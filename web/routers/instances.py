"""CRUD + actions on pfSense instances."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from pfsense_shared.models import Backup, BackupSettings, Instance, Job
from pfsense_shared.schemas import (
    InstanceCreate,
    InstanceRead,
    InstanceUpdate,
    ReloadScheduleCommand,
    RunBackupCommand,
    TestConnectionCommand,
)

from ..dependencies import CryptoDep, CurrentUser, DbSession, Ipc
from ..services import audit
from ..services.cron_utils import validate as validate_cron
from ..services.cron_utils import validate_tz
from ..services.pfsense_preflight import probe as preflight_probe

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/instances", tags=["instances"])


def _to_read(inst: Instance, crypto) -> InstanceRead:
    return InstanceRead.model_validate(
        {
            "id": inst.id,
            "name": inst.name,
            "url": inst.url,
            "username": crypto.decrypt(inst.username_ct),
            "subfolder": inst.subfolder,
            "backup_prefix": inst.backup_prefix,
            "verify_ssl": inst.verify_ssl,
            "timeout_seconds": inst.timeout_seconds,
            "cron_expression": inst.cron_expression,
            "cron_timezone": inst.cron_timezone,
            "enabled": inst.enabled,
            "retention_count": inst.retention_count,
            "compress": inst.compress,
            "created_at": inst.created_at,
            "updated_at": inst.updated_at,
        }
    )


@router.get("", response_model=list[InstanceRead])
async def list_instances(db: DbSession, crypto: CryptoDep) -> list[InstanceRead]:
    rows = (await db.scalars(select(Instance).order_by(Instance.name))).all()
    return [_to_read(r, crypto) for r in rows]


@router.get("/{instance_id}", response_model=InstanceRead)
async def get_instance(instance_id: int, db: DbSession, crypto: CryptoDep) -> InstanceRead:
    inst = await db.get(Instance, instance_id)
    if inst is None:
        raise HTTPException(404, "instance not found")
    return _to_read(inst, crypto)


@router.post("", response_model=InstanceRead, status_code=status.HTTP_201_CREATED)
async def create_instance(
    payload: InstanceCreate, db: DbSession, crypto: CryptoDep, user: CurrentUser, ipc: Ipc
) -> InstanceRead:
    if payload.cron_expression:
        try:
            validate_cron(payload.cron_expression)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
    try:
        validate_tz(payload.cron_timezone)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None

    inst = Instance(
        name=payload.name,
        url=payload.url,
        username_ct=crypto.encrypt(payload.username),
        password_ct=crypto.encrypt(payload.password),
        subfolder=payload.subfolder,
        backup_prefix=payload.backup_prefix,
        verify_ssl=payload.verify_ssl,
        timeout_seconds=payload.timeout_seconds,
        cron_expression=payload.cron_expression,
        cron_timezone=payload.cron_timezone,
        enabled=payload.enabled,
        retention_count=payload.retention_count,
        compress=payload.compress,
    )
    db.add(inst)
    await db.flush()
    audit.record(
        db, actor_email=user["email"], action="create", resource="instance",
        resource_id=inst.id, details={"name": inst.name},
    )
    await db.commit()
    # Register the cron if one was provided.
    if inst.cron_expression:
        await ipc.send(ReloadScheduleCommand(instance_id=inst.id))
    return _to_read(inst, crypto)


@router.put("/{instance_id}", response_model=InstanceRead)
async def update_instance(
    instance_id: int,
    payload: InstanceUpdate,
    db: DbSession,
    crypto: CryptoDep,
    user: CurrentUser,
    ipc: Ipc,
) -> InstanceRead:
    inst = await db.get(Instance, instance_id)
    if inst is None:
        raise HTTPException(404, "instance not found")

    if payload.cron_expression is not None and payload.cron_expression:
        try:
            validate_cron(payload.cron_expression)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
    if payload.cron_timezone is not None:
        try:
            validate_tz(payload.cron_timezone)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    # Track which fields the client actually sent so a deliberate ``null``
    # (e.g. clearing the cron_timezone override) can write through instead
    # of being treated as "not provided". Fields not in ``sent`` are left
    # untouched on the row.
    sent = payload.model_dump(exclude_unset=True)
    changed: dict[str, Any] = {}
    for field in (
        "name", "url", "subfolder", "backup_prefix", "verify_ssl",
        "timeout_seconds", "cron_expression", "cron_timezone",
        "enabled", "retention_count", "compress",
    ):
        if field not in sent:
            continue
        val = sent[field]
        if getattr(inst, field) != val:
            setattr(inst, field, val)
            changed[field] = val
    if payload.username is not None:
        inst.username_ct = crypto.encrypt(payload.username)
        changed["username"] = "<updated>"
    # L2: treat whitespace-only password as "do not change".
    if payload.password and payload.password.strip():
        inst.password_ct = crypto.encrypt(payload.password)
        changed["password"] = "<updated>"

    if not changed:
        return _to_read(inst, crypto)

    inst.updated_at = datetime.now(UTC)
    audit.record(
        db, actor_email=user["email"], action="update", resource="instance",
        resource_id=inst.id, details=changed,
    )
    await db.commit()

    # Any schedule-relevant change → tell the worker to reload.
    # H-adjacent: `name` belongs here too so log output catches the new name.
    if {"cron_expression", "cron_timezone", "enabled", "name"} & changed.keys():
        await ipc.send(ReloadScheduleCommand(instance_id=inst.id))

    return _to_read(inst, crypto)


@router.delete("/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instance(
    instance_id: int, db: DbSession, user: CurrentUser, ipc: Ipc
) -> None:
    inst = await db.get(Instance, instance_id)
    if inst is None:
        raise HTTPException(404, "instance not found")
    name = inst.name
    await db.delete(inst)
    audit.record(
        db, actor_email=user["email"], action="delete", resource="instance",
        resource_id=instance_id, details={"name": name},
    )
    await db.commit()
    await ipc.send(ReloadScheduleCommand(instance_id=instance_id))


class PreflightRequest(BaseModel):
    """Either pass credentials directly (create flow) OR an instance_id
    (edit flow) to re-use the stored creds server-side."""

    instance_id: int | None = None
    url: str | None = None
    username: str | None = None
    password: str | None = None
    verify_ssl: bool = False
    timeout_seconds: int = 15


class PreflightResponse(BaseModel):
    ok: bool
    detail: str
    duration_ms: int


@router.post("/preflight", response_model=PreflightResponse)
async def preflight(
    payload: PreflightRequest,
    db: DbSession,
    crypto: CryptoDep,
    user: CurrentUser,
) -> PreflightResponse:
    """Run a real login flow against the pfSense and classify the result.

    Synchronous to the HTTP request — no worker round-trip — so the
    instance editor can show a green/red status inline before the user
    saves. Credentials are read off the request, or pulled from the DB
    (decrypted with the app's Fernet key) when ``instance_id`` is
    provided.
    """
    url: str | None = payload.url
    username: str | None = payload.username
    password: str | None = payload.password
    verify_ssl = payload.verify_ssl

    if payload.instance_id is not None:
        inst = await db.get(Instance, payload.instance_id)
        if inst is None:
            raise HTTPException(404, "instance not found")
        url = url or inst.url
        username = username or crypto.decrypt(inst.username_ct)
        # Only fall back to the stored password when the caller didn't send one.
        if not password:
            password = crypto.decrypt(inst.password_ct)
        verify_ssl = payload.verify_ssl or inst.verify_ssl

    if not (url and username and password):
        raise HTTPException(400, "url, username and password are required")

    log.info("preflight requested by %s for url=%s", user["email"], url)
    result = await preflight_probe(
        url=url,
        username=username,
        password=password,
        verify_ssl=verify_ssl,
        timeout_seconds=payload.timeout_seconds,
    )
    return PreflightResponse(
        ok=result.ok, detail=result.detail, duration_ms=result.duration_ms
    )


@router.post("/{instance_id}/test-connection")
async def test_connection(
    instance_id: int, db: DbSession, user: CurrentUser, ipc: Ipc
) -> dict[str, int]:
    if (await db.get(Instance, instance_id)) is None:
        raise HTTPException(404, "instance not found")
    job = Job(instance_id=instance_id, kind="test_connection", requested_by=user["email"])
    db.add(job)
    await db.flush()
    audit.record(
        db, actor_email=user["email"], action="trigger", resource="test_connection",
        resource_id=instance_id,
    )
    await db.commit()
    await ipc.send(TestConnectionCommand(instance_id=instance_id, job_id=job.id))
    return {"job_id": job.id}


@router.post("/{instance_id}/backup-now")
async def backup_now(
    instance_id: int, db: DbSession, user: CurrentUser, ipc: Ipc
) -> dict[str, int]:
    if (await db.get(Instance, instance_id)) is None:
        raise HTTPException(404, "instance not found")
    job = Job(instance_id=instance_id, kind="manual", requested_by=user["email"])
    db.add(job)
    await db.flush()
    audit.record(
        db, actor_email=user["email"], action="trigger", resource="backup",
        resource_id=instance_id,
    )
    await db.commit()
    await ipc.send(RunBackupCommand(instance_id=instance_id, job_id=job.id))
    return {"job_id": job.id}


class ImportBackupsResult(BaseModel):
    imported: int
    skipped: int
    scanned_dir: str


@router.post("/{instance_id}/import-backups", response_model=ImportBackupsResult)
async def import_backups(
    instance_id: int, db: DbSession, user: CurrentUser
) -> ImportBackupsResult:
    """Adopt pre-existing backup files on disk into this instance's Backup rows.

    Scans the instance's backup directory (``{BackupSettings.directory}`` joined
    with ``Instance.subfolder`` if set), non-recursively, for ``*.xml`` and
    ``*.xml.gz`` files. Each unseen file (by absolute path) gets a Backup row
    with ``success=True``, size from ``st_size``, and mtime mapped to both
    ``started_at`` and ``finished_at``. Files already referenced by any existing
    Backup row are skipped so a shared directory doesn't double-adopt across
    instances.
    """
    inst = await db.get(Instance, instance_id)
    if inst is None:
        raise HTTPException(404, "instance not found")

    bs = await db.get(BackupSettings, 1)
    root = Path(bs.directory if bs is not None else "/backups")
    scan_dir = root / inst.subfolder if inst.subfolder else root

    if not scan_dir.is_dir():
        raise HTTPException(404, f"backup directory not found on disk: {scan_dir}")

    candidates: list[Path] = sorted(
        p for p in scan_dir.iterdir()
        if p.is_file() and (p.suffix == ".xml" or p.name.endswith(".xml.gz"))
    )

    existing_paths: set[str] = set(
        (await db.scalars(select(Backup.path))).all()
    )

    imported = 0
    skipped = 0
    for p in candidates:
        abs_path = str(p.resolve())
        if abs_path in existing_paths:
            skipped += 1
            continue
        stat = p.stat()
        ts = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        db.add(
            Backup(
                instance_id=inst.id,
                job_id=None,
                started_at=ts,
                finished_at=ts,
                duration_seconds=0.0,
                filename=p.name,
                path=abs_path,
                size_bytes=stat.st_size,
                compressed=p.name.endswith(".gz"),
                success=True,
                error_message=None,
            )
        )
        imported += 1

    audit.record(
        db, actor_email=user["email"], action="trigger", resource="import_backups",
        resource_id=inst.id,
        details={"imported": imported, "skipped": skipped, "scanned_dir": str(scan_dir)},
    )
    await db.commit()
    log.info(
        "import_backups instance=%s dir=%s imported=%d skipped=%d",
        inst.name, scan_dir, imported, skipped,
    )
    return ImportBackupsResult(
        imported=imported, skipped=skipped, scanned_dir=str(scan_dir)
    )
