"""CRUD + actions on pfSense instances."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from pfsense_shared.models import Backup, BackupSettings, Instance, Job, Notification
from pfsense_shared.schemas import (
    BackupOverrides,
    InstanceCreate,
    InstanceRead,
    InstanceUpdate,
    ReencryptBackupsCommand,
    ReloadScheduleCommand,
    RunBackupCommand,
    TestConnectionCommand,
)

from ..dependencies import CryptoDep, CurrentUser, DbSession, Ipc
from ..services import audit
from ..services.cron_utils import validate as validate_cron
from ..services.cron_utils import validate_tz
from ..services.pfsense_preflight import probe as preflight_probe

# Sentinel returned by InstanceRead when a secret is stored; the editor
# sends it back unchanged to signal "keep what's already there".
_SECRET_SENTINEL = "__set__"

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/instances", tags=["instances"])


def _to_read(inst: Instance, crypto) -> InstanceRead:
    # A corrupted / re-keyed ``username_ct`` would otherwise raise
    # ``cryptography.fernet.InvalidToken`` into ``list_instances``
    # and 500 the entire list, taking the UI down. Surface a sentinel
    # for the affected row so operators can still see the instance and
    # fix / delete it. The credentials are already unusable by this
    # point, so no information is lost.
    try:
        username = crypto.decrypt(inst.username_ct)
    except Exception:
        log.warning(
            "instance id=%s username_ct could not be decrypted — "
            "emitting sentinel in read model",
            inst.id,
        )
        username = "<decryption failed>"
    return InstanceRead.model_validate(
        {
            "id": inst.id,
            "name": inst.name,
            "url": inst.url,
            "username": username,
            "subfolder": inst.subfolder,
            "backup_prefix": inst.backup_prefix,
            "verify_ssl": inst.verify_ssl,
            "timeout_seconds": inst.timeout_seconds,
            "cron_expression": inst.cron_expression,
            "cron_timezone": inst.cron_timezone,
            "enabled": inst.enabled,
            "retention_count": inst.retention_count,
            "compress": inst.compress,
            "backup_area": inst.backup_area or "",
            "backup_include_rrd": inst.backup_include_rrd,
            "backup_include_packages": inst.backup_include_packages,
            "backup_include_ssh": inst.backup_include_ssh,
            "backup_encrypt": inst.backup_encrypt,
            # Redact: emit the sentinel when a ciphertext is present, else None.
            "backup_encrypt_password": (
                _SECRET_SENTINEL if inst.backup_encrypt_password_ct else None
            ),
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

    # Encryption needs a password. Refuse the create rather than
    # committing a row the worker can't actually use.
    encrypt_password_ct: bytes | None = None
    if payload.backup_encrypt:
        if not payload.backup_encrypt_password or not payload.backup_encrypt_password.strip():
            raise HTTPException(400, "backup_encrypt=true requires a backup_encrypt_password")
        encrypt_password_ct = crypto.encrypt(payload.backup_encrypt_password)
    elif payload.backup_encrypt_password:
        # Disallow sending a password without enabling encryption — keeps
        # the stored state unambiguous.
        raise HTTPException(
            400, "backup_encrypt_password was provided but backup_encrypt is false"
        )

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
        backup_area=payload.backup_area,
        backup_include_rrd=payload.backup_include_rrd,
        backup_include_packages=payload.backup_include_packages,
        backup_include_ssh=payload.backup_include_ssh,
        backup_encrypt=payload.backup_encrypt,
        backup_encrypt_password_ct=encrypt_password_ct,
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


@router.put("/{instance_id}")
async def update_instance(
    instance_id: int,
    payload: InstanceUpdate,
    db: DbSession,
    crypto: CryptoDep,
    user: CurrentUser,
    ipc: Ipc,
) -> dict[str, Any]:
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
        "backup_area", "backup_include_rrd", "backup_include_packages",
        "backup_include_ssh",
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

    # Encryption password: "__set__" = no-op (keep ciphertext), None =
    # clear, any other string = new plaintext to Fernet-encrypt.
    password_actually_changed = False
    if "backup_encrypt_password" in sent:
        pw = payload.backup_encrypt_password
        if pw == _SECRET_SENTINEL:
            pass  # keep existing ciphertext
        elif pw is None or (isinstance(pw, str) and pw == ""):
            if inst.backup_encrypt_password_ct is not None:
                inst.backup_encrypt_password_ct = None
                changed["backup_encrypt_password"] = "<cleared>"
                password_actually_changed = True
        else:
            inst.backup_encrypt_password_ct = crypto.encrypt(pw)
            changed["backup_encrypt_password"] = "<updated>"
            password_actually_changed = True

    if "backup_encrypt" in sent and inst.backup_encrypt != sent["backup_encrypt"]:
        inst.backup_encrypt = sent["backup_encrypt"]
        changed["backup_encrypt"] = sent["backup_encrypt"]
        # When encryption is turned off, clear any stored ciphertext on
        # the same save so we don't leave an orphan password sitting on a
        # disabled row. The UI may send ``"__set__"`` if the user didn't
        # touch the password field — we still drop it here because the
        # operator's intent is "stop encrypting."
        if not inst.backup_encrypt and inst.backup_encrypt_password_ct is not None:
            inst.backup_encrypt_password_ct = None
            changed["backup_encrypt_password"] = "<cleared>"
            password_actually_changed = True

    # Invariant check after everything's applied: if encryption is on,
    # a ciphertext must exist. Refuse saves that would leave the row in
    # a non-runnable state (encrypt=on, no password).
    if inst.backup_encrypt and inst.backup_encrypt_password_ct is None:
        raise HTTPException(
            400,
            "backup_encrypt=true requires a backup_encrypt_password "
            "(send the new plaintext or keep the existing one via '__set__').",
        )

    if not changed:
        return _to_read(inst, crypto).model_dump()

    inst.updated_at = datetime.now(UTC)
    audit.record(
        db, actor_email=user["email"], action="update", resource="instance",
        resource_id=inst.id, details=changed,
    )

    # Fire a re-encrypt Job when the operator ticked the box AND the
    # password actually moved. Do it in the same commit so a subsequent
    # worker restart can still resume from a consistent state.
    reencrypt_job_id: int | None = None
    if payload.reencrypt_existing_backups and password_actually_changed:
        if not inst.backup_encrypt or inst.backup_encrypt_password_ct is None:
            raise HTTPException(
                400,
                "re-encrypt requested but encryption is not enabled on this instance",
            )
        job = Job(
            instance_id=inst.id,
            kind="reencrypt",
            requested_by=user["email"],
        )
        db.add(job)
        await db.flush()
        reencrypt_job_id = job.id

    await db.commit()

    # Any schedule-relevant change → tell the worker to reload.
    # H-adjacent: `name` belongs here too so log output catches the new name.
    if {"cron_expression", "cron_timezone", "enabled", "name"} & changed.keys():
        await ipc.send(ReloadScheduleCommand(instance_id=inst.id))

    if reencrypt_job_id is not None:
        await ipc.send(
            ReencryptBackupsCommand(instance_id=inst.id, job_id=reencrypt_job_id)
        )

    payload_dict = _to_read(inst, crypto).model_dump()
    if reencrypt_job_id is not None:
        # The frontend uses this to open the progress toast + poll /jobs.
        payload_dict["reencrypt_job_id"] = reencrypt_job_id
    return payload_dict


@router.delete("/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instance(
    instance_id: int, db: DbSession, user: CurrentUser, ipc: Ipc
) -> None:
    inst = await db.get(Instance, instance_id)
    if inst is None:
        raise HTTPException(404, "instance not found")
    name = inst.name

    # Prune this ID from every scoped notification so the scope filter
    # doesn't carry a dangling reference. Empty lists get cleared so
    # the "null = all" shortcut stays unambiguous.
    scoped = (
        await db.scalars(
            select(Notification).where(Notification.instance_ids_json.is_not(None))
        )
    ).all()
    for n in scoped:
        try:
            ids = json.loads(n.instance_ids_json or "[]")
        except (TypeError, ValueError):
            continue
        if instance_id in ids:
            ids = [i for i in ids if i != instance_id]
            n.instance_ids_json = json.dumps(ids) if ids else None

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


class BackupNowRequest(BaseModel):
    """Optional one-shot overrides for a manual "Backup now" run.

    Any field left unset inherits the stored Instance value; none of
    these are persisted back to the Instance row.
    """

    backup_area: str | None = None
    backup_include_rrd: bool | None = None
    backup_include_packages: bool | None = None
    backup_include_ssh: bool | None = None
    backup_encrypt: bool | None = None
    # Plaintext on the wire; we Fernet-encrypt before shipping the IPC.
    backup_encrypt_password: str | None = None


def _build_overrides(
    req: BackupNowRequest | None, crypto
) -> BackupOverrides | None:
    """Translate a web-side override request into a wire-safe BackupOverrides.

    Returns None when the caller didn't set anything — avoids paying
    the IPC cost for default runs.
    """
    if req is None:
        return None
    set_fields = req.model_dump(exclude_unset=True)
    if not set_fields:
        return None
    ct: bytes | None = None
    if "backup_encrypt_password" in set_fields:
        pw = set_fields["backup_encrypt_password"]
        if pw:
            ct = crypto.encrypt(pw)
    return BackupOverrides(
        backup_area=set_fields.get("backup_area"),
        backup_include_rrd=set_fields.get("backup_include_rrd"),
        backup_include_packages=set_fields.get("backup_include_packages"),
        backup_include_ssh=set_fields.get("backup_include_ssh"),
        backup_encrypt=set_fields.get("backup_encrypt"),
        backup_encrypt_password_ct=ct,
    )


@router.post("/{instance_id}/backup-now")
async def backup_now(
    instance_id: int,
    db: DbSession,
    user: CurrentUser,
    ipc: Ipc,
    crypto: CryptoDep,
    overrides: BackupNowRequest | None = None,
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
    await ipc.send(
        RunBackupCommand(
            instance_id=instance_id,
            job_id=job.id,
            overrides=_build_overrides(overrides, crypto),
        )
    )
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
        # Adopted files have no capture-time provenance; the Backup
        # row defaults (area="", rrd=False, packages=True, ssh=True,
        # encrypted=False) describe "unknown but assume historical
        # behavior" which matches how these files were produced
        # before this version shipped.
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
