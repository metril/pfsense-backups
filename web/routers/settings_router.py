"""Global backup/file-layout settings + logging settings (singleton rows)."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from pfsense_shared.models import BackupSettings, LoggingSettings, ReplicationSettings
from pfsense_shared.schemas import (
    BackupSettingsRead,
    BackupSettingsUpdate,
    LoggingSettingsRead,
    LoggingSettingsUpdate,
    ReloadScheduleCommand,
    ReplicationSettingsRead,
    ReplicationSettingsUpdate,
    TestReplicationCommand,
)

from ..dependencies import CryptoDep, CurrentUser, DbSession, Ipc
from ..services import audit
from ..services.cron_utils import validate_tz

router = APIRouter(prefix="/api/settings", tags=["settings"])

_SECRET_SENTINEL = "__set__"


def _replication_to_read(row: ReplicationSettings | None) -> ReplicationSettingsRead:
    if row is None:
        row = ReplicationSettings(id=1)

    def sent(ct: bytes | None) -> str | None:
        return _SECRET_SENTINEL if ct else None

    return ReplicationSettingsRead(
        enabled=row.enabled,
        kind=row.kind,  # type: ignore[arg-type]
        s3_endpoint_url=row.s3_endpoint_url,
        s3_region=row.s3_region,
        s3_bucket=row.s3_bucket,
        s3_access_key_id=row.s3_access_key_id,
        s3_secret_access_key=sent(row.s3_secret_access_key_ct),
        sftp_host=row.sftp_host,
        sftp_port=row.sftp_port,
        sftp_username=row.sftp_username,
        sftp_password=sent(row.sftp_password_ct),
        sftp_private_key=sent(row.sftp_private_key_ct),
        base_path=row.base_path,
        encrypt_plaintext=row.encrypt_plaintext,
        double_encrypt=row.double_encrypt,
        replication_password=sent(row.replication_password_ct),
        mirror_deletes=row.mirror_deletes,
    )


@router.get("")
async def get_all(db: DbSession) -> dict[str, Any]:
    bs = await db.get(BackupSettings, 1)
    ls = await db.get(LoggingSettings, 1)
    rs = await db.get(ReplicationSettings, 1)
    return {
        "backup": BackupSettingsRead.model_validate(bs).model_dump() if bs else None,
        "logging": LoggingSettingsRead.model_validate(ls).model_dump() if ls else None,
        "replication": _replication_to_read(rs).model_dump(),
    }


@router.put("/backup", response_model=BackupSettingsRead)
async def put_backup(
    payload: BackupSettingsUpdate, db: DbSession, user: CurrentUser, ipc: Ipc
) -> BackupSettingsRead:
    row = await db.get(BackupSettings, 1)
    if row is None:
        row = BackupSettings(id=1)
        db.add(row)
    # Validate tz BEFORE we start mutating the row so a bad zone doesn't
    # partially apply.
    if payload.default_timezone is not None:
        try:
            validate_tz(payload.default_timezone)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    changed: dict[str, Any] = {}
    for field in (
        "filename_format",
        "timestamp_format",
        "directory",
        "default_timezone",
        "backup_all_max_workers",
    ):
        val = getattr(payload, field)
        if val is not None and getattr(row, field, None) != val:
            setattr(row, field, val)
            changed[field] = val
    if changed:
        audit.record(
            db, actor_email=user["email"], action="update", resource="backup_settings",
            resource_id=1, details=changed,
        )
    await db.commit()
    # Default timezone change affects every instance that inherits it, so
    # kick the scheduler to re-bind all cron triggers with the new tz.
    if "default_timezone" in changed:
        await ipc.send(ReloadScheduleCommand(instance_id=None))
    return BackupSettingsRead.model_validate(row)


@router.put("/replication", response_model=ReplicationSettingsRead)
async def put_replication(
    payload: ReplicationSettingsUpdate,
    db: DbSession,
    crypto: CryptoDep,
    user: CurrentUser,
) -> ReplicationSettingsRead:
    row = await db.get(ReplicationSettings, 1)
    if row is None:
        row = ReplicationSettings(id=1)
        db.add(row)

    sent = payload.model_dump(exclude_unset=True)
    changed: dict[str, Any] = {}

    for field in (
        "enabled", "kind", "s3_endpoint_url", "s3_region", "s3_bucket",
        "s3_access_key_id", "sftp_host", "sftp_port", "sftp_username",
        "base_path", "encrypt_plaintext", "double_encrypt", "mirror_deletes",
    ):
        if field not in sent:
            continue
        val = sent[field]
        if getattr(row, field) != val:
            setattr(row, field, val)
            changed[field] = val

    # Secrets: "__set__" sentinel = keep, None/"" = clear, else encrypt.
    for plain_field, ct_field in (
        ("s3_secret_access_key", "s3_secret_access_key_ct"),
        ("sftp_password", "sftp_password_ct"),
        ("sftp_private_key", "sftp_private_key_ct"),
        ("replication_password", "replication_password_ct"),
    ):
        if plain_field not in sent:
            continue
        val = sent[plain_field]
        if val == _SECRET_SENTINEL:
            continue
        if not val:
            if getattr(row, ct_field) is not None:
                setattr(row, ct_field, None)
                changed[plain_field] = "<cleared>"
        else:
            setattr(row, ct_field, crypto.encrypt(val))
            changed[plain_field] = "<updated>"

    # The user constraint, enforced at the settings layer: replication
    # cannot be enabled while encrypt_plaintext (or double_encrypt) is
    # on with no replication password — a plaintext local backup must
    # never land plaintext off-site, and "on but unkeyed" would either
    # silently skip uploads or silently disable the wrapping.
    if row.enabled and (row.encrypt_plaintext or row.double_encrypt):
        if row.replication_password_ct is None:
            await db.rollback()
            raise HTTPException(
                400,
                "replication encryption is on but no replication password "
                "is set — set one (or explicitly disable encrypt_plaintext)",
            )

    if changed:
        audit.record(
            db, actor_email=user["email"], action="update",
            resource="replication_settings", resource_id=1, details=changed,
        )
    await db.commit()
    return _replication_to_read(row)


@router.post("/replication/test")
async def test_replication(
    request: Request, user: CurrentUser, ipc: Ipc
) -> dict[str, Any]:
    """Round-trip a connectivity check through the worker (the process
    that actually uploads) and await its result on the event bus."""
    bus = request.app.state.event_bus
    rid = uuid4().hex
    queue = await bus.subscribe()
    try:
        await ipc.send(TestReplicationCommand(request_id=rid))
        deadline = time.monotonic() + 20.0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HTTPException(504, "worker did not respond to the test")
            try:
                envelope = await asyncio.wait_for(queue.get(), timeout=remaining)
            except TimeoutError:
                raise HTTPException(
                    504, "worker did not respond to the test"
                ) from None
            if (
                envelope.get("topic") == "replication_test.result"
                and envelope.get("request_id") == rid
            ):
                return {"ok": envelope.get("ok"), "detail": envelope.get("detail")}
    finally:
        await bus.unsubscribe(queue)


@router.put("/logging", response_model=LoggingSettingsRead)
async def put_logging(
    payload: LoggingSettingsUpdate, db: DbSession, user: CurrentUser
) -> LoggingSettingsRead:
    row = await db.get(LoggingSettings, 1)
    if row is None:
        row = LoggingSettings(id=1)
        db.add(row)
    changed: dict[str, Any] = {}
    for field in ("level", "format"):
        val = getattr(payload, field)
        if val is not None and getattr(row, field, None) != val:
            setattr(row, field, val)
            changed[field] = val
    if changed:
        audit.record(
            db, actor_email=user["email"], action="update", resource="logging_settings",
            resource_id=1, details=changed,
        )
    await db.commit()
    return LoggingSettingsRead.model_validate(row)
