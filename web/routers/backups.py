"""Browse, download (single + zip), and diff backup XML files."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pfsense_shared.anchor_events import section_for_anchor
from pfsense_shared.backup_diff_storage import (
    compute_diff,
    decode_diff,
    encode_diff,
    read_backup_bytes,
    summarise_diff,
)
from pfsense_shared.models import AnchorEvent, Backup, BackupDiff, Instance, Job
from pfsense_shared.paths import BACKUPS_DIR  # noqa: F401 — used by /anchor-history
from pfsense_shared.pfsense_anchor_values import resolve_anchor_value
from pfsense_shared.pfsense_crypto import (
    PfSenseCryptoError,
    decrypt_pfsense_backup,
    looks_encrypted,
)
from pfsense_shared.pfsense_diff import ConfigDiff, diff_configs
from pfsense_shared.pfsense_labels import label_for_section
from pfsense_shared.pfsense_parser import ParsedConfig, PfSenseParseError
from pfsense_shared.pfsense_parser import parse as parse_pfsense_xml
from pfsense_shared.pfsense_positions import build_positions
from pfsense_shared.schemas import (
    BackupUpdate,
    DeleteReplicaObjectCommand,
    ReencryptAllBackupsCommand,
    RetrieveReplicaCommand,
    RunBackupAllCommand,
)

from ..dependencies import CryptoDep, CurrentUser, DbSession, Ipc
from ..services import audit
from ..services.backup_storage import read_content, stream_raw, zip_stream

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backups", tags=["backups"])


class DiffCounts(BaseModel):
    added: int
    removed: int
    modified: int


class BackupListItem(BaseModel):
    id: int
    instance_id: int
    instance_name: str
    started_at: str
    finished_at: str
    duration_seconds: float
    filename: str
    size_bytes: int
    compressed: bool
    success: bool
    tag: str | None = None
    note: str | None = None

    # Contents snapshot — mirrors what was captured at run time.
    area: str = ""
    included_rrd: bool = False
    included_packages: bool = True
    included_ssh: bool = True
    encrypted: bool = False
    config_version: str | None = None
    # F3: off-site replication state. ``location`` is derived for the
    # UI: local / both / offsite (the list filter keys on it).
    replica_status: str | None = None
    local_present: bool = True


class BackupHistoryItem(BaseModel):
    """Lean per-row payload for the per-instance scrubber.

    The scrubber only needs ``id`` (navigation + diff fetch),
    ``started_at`` (timeline label), ``size_bytes`` (focused
    summary), ``tag`` (focused badge), and ``changes_since_first``
    (the "since first" cluster) — five fields vs. BackupListItem's
    twenty-two. Stripping the rest cuts the payload by roughly 4×
    on a 200-backup history.
    """

    id: int
    started_at: str
    size_bytes: int
    tag: str | None = None
    changes_since_first: DiffCounts | None = None
    config_version: str | None = None


class ZipRequest(BaseModel):
    ids: list[int]


class BackupAllRequest(BaseModel):
    """Optional overrides applied uniformly to every instance in the sweep."""

    backup_area: str | None = None
    backup_include_rrd: bool | None = None
    backup_include_packages: bool | None = None
    backup_include_ssh: bool | None = None
    backup_encrypt: bool | None = None
    backup_encrypt_password: str | None = None


class ReencryptAllRequest(BaseModel):
    new_password: str
    # Confirm field kept even though the UI will already have checked —
    # a typo mismatch here gives a 400 instead of silent acceptance.
    confirm_password: str
    also_update_instance_passwords: bool = True


@router.post("/run-all")
async def run_all_backups(
    db: DbSession,
    user: CurrentUser,
    ipc: Ipc,
    crypto: CryptoDep,
    overrides: BackupAllRequest | None = None,
) -> dict[str, int]:
    """Kick off a parallel backup sweep across every enabled instance.

    Returns immediately with the parent Job id; per-instance progress
    arrives on the existing /api/events WebSocket stream. Optional
    `overrides` apply the same one-shot settings to every instance
    without touching their stored configuration.
    """
    from pfsense_shared.schemas import BackupOverrides

    job = Job(kind="run_backup_all", requested_by=user["email"])
    db.add(job)
    await db.flush()
    audit.record(
        db, actor_email=user["email"], action="trigger",
        resource="backup_all", resource_id=None,
    )
    await db.commit()

    ipc_overrides: BackupOverrides | None = None
    if overrides is not None:
        sent = overrides.model_dump(exclude_unset=True)
        if sent:
            ct: bytes | None = None
            if "backup_encrypt_password" in sent and sent["backup_encrypt_password"]:
                ct = crypto.encrypt(sent["backup_encrypt_password"])
            ipc_overrides = BackupOverrides(
                backup_area=sent.get("backup_area"),
                backup_include_rrd=sent.get("backup_include_rrd"),
                backup_include_packages=sent.get("backup_include_packages"),
                backup_include_ssh=sent.get("backup_include_ssh"),
                backup_encrypt=sent.get("backup_encrypt"),
                backup_encrypt_password_ct=ct,
            )

    await ipc.send(RunBackupAllCommand(job_id=job.id, overrides=ipc_overrides))
    return {"job_id": job.id}


@router.post("/reencrypt-all")
async def reencrypt_all(
    body: ReencryptAllRequest,
    db: DbSession,
    user: CurrentUser,
    ipc: Ipc,
    crypto: CryptoDep,
) -> dict[str, int]:
    """Re-encrypt every encrypted Backup across every instance.

    Creates a parent Job and hands the worker a Fernet-encrypted copy
    of the new password. When ``also_update_instance_passwords`` is
    True (default), each encrypted Instance's stored password gets
    flipped to the new one in the same run so future backups keep
    working without extra configuration.
    """
    if body.new_password != body.confirm_password:
        raise HTTPException(400, "new_password and confirm_password must match")
    if not body.new_password or not body.new_password.strip():
        raise HTTPException(400, "new_password must not be blank")

    job = Job(kind="reencrypt_all", requested_by=user["email"])
    db.add(job)
    await db.flush()
    audit.record(
        db, actor_email=user["email"], action="trigger",
        resource="reencrypt_all", resource_id=None,
        details={"also_update_instance_passwords": body.also_update_instance_passwords},
    )
    await db.commit()

    await ipc.send(
        ReencryptAllBackupsCommand(
            job_id=job.id,
            new_password_ct=crypto.encrypt(body.new_password),
            also_update_instance_passwords=body.also_update_instance_passwords,
        )
    )
    return {"job_id": job.id}


# Columns the UI can ask to sort by. Restricted to indexed / lightweight
# columns so we don't hand the user arbitrary ORDER BY targets.
_SORTABLE = {
    "started_at": Backup.started_at,
    "size_bytes": Backup.size_bytes,
    "duration_seconds": Backup.duration_seconds,
    "filename": Backup.filename,
}


@router.get("", response_model=list[BackupListItem])
async def list_backups(
    db: DbSession,
    instance_id: int | None = None,
    # started_from / started_to: ISO-8601 inclusive bounds on started_at.
    started_from: datetime | None = None,
    started_to: datetime | None = None,
    sort: str = "started_at",
    order: str = "desc",
    # v0.45.0: the 100-row default + ``le=500`` cap is gone. The
    # global Backups page loads the full set so operators can sort
    # / filter across all history. ``limit`` stays as an opt-in
    # query param for callers that explicitly want paging.
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[BackupListItem]:
    col = _SORTABLE.get(sort, Backup.started_at)
    direction = col.desc() if order.lower() == "desc" else col.asc()
    # The "+N since first" diff JOIN that used to live here is gone
    # in v0.45.0 — the global Backups table doesn't render that
    # column, and the per-instance scrubber moved to its own lean
    # ``/api/backups/history`` endpoint (which keeps the JOIN
    # because *it* renders the cluster).
    stmt = (
        select(Backup, Instance.name)
        .join(Instance, Backup.instance_id == Instance.id)
        .order_by(direction)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    if offset:
        stmt = stmt.offset(offset)
    if instance_id is not None:
        stmt = stmt.where(Backup.instance_id == instance_id)
    if started_from is not None:
        stmt = stmt.where(Backup.started_at >= started_from)
    if started_to is not None:
        stmt = stmt.where(Backup.started_at <= started_to)
    rows = (await db.execute(stmt)).all()
    out: list[BackupListItem] = []
    for b, name in rows:
        out.append(
            BackupListItem(
                id=b.id,
                instance_id=b.instance_id,
                instance_name=name,
                started_at=b.started_at.isoformat(),
                finished_at=b.finished_at.isoformat(),
                duration_seconds=b.duration_seconds,
                filename=b.filename,
                size_bytes=b.size_bytes,
                compressed=b.compressed,
                success=b.success,
                tag=b.tag,
                note=b.note,
                area=b.area or "",
                included_rrd=b.included_rrd,
                included_packages=b.included_packages,
                included_ssh=b.included_ssh,
                encrypted=b.encrypted,
                config_version=b.config_version,
                replica_status=b.replica_status,
                local_present=b.local_present,
            )
        )
    return out


@router.get("/history", response_model=list[BackupHistoryItem])
async def list_backup_history(
    db: DbSession,
    instance_id: int = Query(...),
) -> list[BackupHistoryItem]:
    """Per-instance scrubber feed.

    Returns every successful backup for the instance in ASC
    chronological order, with only the fields the scrubber renders
    (id, started_at, size_bytes, tag, changes_since_first). No
    limit / offset / sort / order knobs — the v0.45.0 scrubber is
    "always all, always ascending". The composite index
    ``ix_backups_instance_started`` keeps the query cheap at
    thousands of rows.
    """
    stmt = (
        select(
            Backup.id,
            Backup.started_at,
            Backup.size_bytes,
            Backup.tag,
            Backup.config_version,
            BackupDiff.added_count,
            BackupDiff.removed_count,
            BackupDiff.modified_count,
        )
        .outerjoin(
            BackupDiff,
            (BackupDiff.backup_id == Backup.id) & (BackupDiff.kind == "first"),
        )
        .where(Backup.instance_id == instance_id)
        .where(Backup.success.is_(True))
        .order_by(Backup.started_at.asc())
    )
    rows = (await db.execute(stmt)).all()
    out: list[BackupHistoryItem] = []
    for bid, started, size, tag, config_version, added, removed, modified in rows:
        counts: DiffCounts | None = None
        if added is not None and removed is not None and modified is not None:
            counts = DiffCounts(added=added, removed=removed, modified=modified)
        out.append(
            BackupHistoryItem(
                id=bid,
                started_at=started.isoformat(),
                size_bytes=size,
                tag=tag,
                changes_since_first=counts,
                config_version=config_version,
            )
        )
    return out


async def _load(db: AsyncSession, backup_id: int) -> tuple[Backup, Path]:
    b = await db.get(Backup, backup_id)
    if b is None:
        raise HTTPException(404, "backup not found")
    path = Path(b.path)
    # ``stat`` is blocking — punt to a thread so a stalled mount
    # (NFS, slow backing store) doesn't hang the event loop.
    exists = await asyncio.to_thread(path.is_file)
    if not exists:
        # M6: 404 is the correct semantic here (the resource doesn't exist at
        # the moment of the request). 410 implies permanent tombstone.
        # Don't leak the absolute container path into the response body —
        # it reveals the data-volume layout to authenticated clients. The
        # server-side log entry below captures the path for operators.
        log.warning(
            "_load id=%d reports path=%s but file is missing on disk",
            backup_id, path,
        )
        raise HTTPException(404, "backup file not found on disk")
    return b, path


async def _load_and_snapshot(db: AsyncSession, backup_id: int) -> _BackupWalkRow:
    """Load a Backup, validate its on-disk file exists, and return a
    plain Pydantic snapshot safe to use after the session closes.

    The caller is expected to ``await db.close()`` (or release the
    connection some other way) before doing heavy decrypt / parse
    work — see v0.45.1 pool-discipline rewrite. The snapshot carries
    every field ``_read_for_walk`` + ``_row_path`` need; ORM
    attribute access after the session closes would lazy-load and
    blow up, so we copy out here.
    """
    row, _ = await _load(db, backup_id)
    return _BackupWalkRow(
        id=row.id,
        started_at=row.started_at,
        path=row.path,
        compressed=row.compressed,
        encrypted=row.encrypted,
        encrypt_password_ct=row.encrypt_password_ct,
    )


@router.get("/{backup_id}")
async def get_backup(backup_id: int, db: DbSession) -> dict[str, Any]:
    b, _ = await _load(db, backup_id)
    return {
        "id": b.id,
        "instance_id": b.instance_id,
        "started_at": b.started_at.isoformat(),
        "finished_at": b.finished_at.isoformat(),
        "duration_seconds": b.duration_seconds,
        "filename": b.filename,
        # NB: the absolute on-disk path stays server-side — the UI only
        # needs ``filename``, and leaking the data-volume layout to the
        # client buys nothing.
        "size_bytes": b.size_bytes,
        "compressed": b.compressed,
        "success": b.success,
        "error_message": b.error_message,
        "tag": b.tag,
        "note": b.note,
        "area": b.area or "",
        "included_rrd": b.included_rrd,
        "included_packages": b.included_packages,
        "included_ssh": b.included_ssh,
        "config_version": b.config_version,
        "encrypted": b.encrypted,
    }


@router.patch("/{backup_id}")
async def patch_backup(
    backup_id: int, payload: BackupUpdate, db: DbSession, user: CurrentUser
) -> dict[str, Any]:
    """Edit the user-provided metadata (tag + note). Path/size/etc. stay read-only."""
    b = await db.get(Backup, backup_id)
    if b is None:
        raise HTTPException(404, "backup not found")

    changed: dict[str, Any] = {}
    patch = payload.model_dump(exclude_unset=True)
    if "tag" in patch:
        # Treat empty/whitespace as "clear" so the UI can delete a label.
        tag = patch["tag"]
        tag = tag.strip() if isinstance(tag, str) else tag
        if tag == "":
            tag = None
        if b.tag != tag:
            b.tag = tag
            changed["tag"] = tag
    if "note" in patch:
        note = patch["note"]
        if isinstance(note, str) and note.strip() == "":
            note = None
        if b.note != note:
            b.note = note
            # Audit the fact of the edit, not the text (may be long/sensitive).
            changed["note"] = "<updated>" if note else "<cleared>"

    if changed:
        audit.record(
            db, actor_email=user["email"], action="update", resource="backup",
            resource_id=b.id, details=changed,
        )
        await db.commit()

    return {"id": b.id, "tag": b.tag, "note": b.note}


@router.delete("/{backup_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_backup(
    backup_id: int, db: DbSession, user: CurrentUser, ipc: Ipc
) -> Response:
    """Remove the backup row + the file on disk.

    Mirrors the retention-cleanup behavior in worker/backup_manager.py:
    both the DB row and the on-disk artifact are removed together so the
    list stays in sync with the filesystem.
    """
    b = await db.get(Backup, backup_id)
    if b is None:
        raise HTTPException(404, "backup not found")

    path = Path(b.path)
    file_removed = False
    file_missing = False
    try:
        path.unlink()
        file_removed = True
    except FileNotFoundError:
        file_missing = True
    except OSError as exc:
        # Filesystem refusal (perms, read-only volume) — surface rather
        # than silently orphan the DB row.
        log.error("delete_backup id=%d path=%s unlink failed: %s", b.id, path, exc)
        raise HTTPException(500, f"could not delete file on disk: {exc}") from exc

    filename = b.filename
    instance_id = b.instance_id
    # F3: manual delete removes the off-site copy too (best-effort via
    # the worker, which owns the transports). The confirm dialog in the
    # UI calls out the off-site copy when one exists.
    replica_key = b.replica_key if b.replica_status == "done" else None
    await db.delete(b)
    audit.record(
        db, actor_email=user["email"], action="delete", resource="backup",
        resource_id=backup_id,
        details={
            "filename": filename,
            "instance_id": instance_id,
            "file_removed": file_removed,
            "file_missing": file_missing,
            "replica_deleted": bool(replica_key),
        },
    )
    await db.commit()
    if replica_key:
        await ipc.send(DeleteReplicaObjectCommand(replica_key=replica_key))
    log.info(
        "Deleted backup id=%d filename=%s (file_removed=%s file_missing=%s)",
        backup_id, filename, file_removed, file_missing,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{backup_id}/retrieve")
async def retrieve_backup(
    backup_id: int, db: DbSession, user: CurrentUser, ipc: Ipc
) -> dict[str, Any]:
    """Bring an off-site-only backup back to local storage (F3). The
    worker downloads, sha256-verifies, strips the replication
    encryption layer(s), restores the original file shape, and flips
    ``local_present`` back on; progress lands as a Job."""
    b = await db.get(Backup, backup_id)
    if b is None:
        raise HTTPException(404, "backup not found")
    if b.local_present:
        raise HTTPException(409, "backup is already present locally")
    if b.replica_status != "done" or not b.replica_key:
        raise HTTPException(409, "no verified off-site copy recorded for this backup")

    job = Job(
        instance_id=b.instance_id, kind="retrieve_replica",
        requested_by=user["email"],
    )
    db.add(job)
    await db.flush()
    audit.record(
        db, actor_email=user["email"], action="trigger",
        resource="backup_retrieve", resource_id=backup_id,
        details={"filename": b.filename, "replica_key": b.replica_key},
    )
    await db.commit()
    await ipc.send(RetrieveReplicaCommand(backup_id=backup_id, job_id=job.id))
    return {"job_id": job.id}


@router.get("/{backup_id}/content")
async def get_content(
    backup_id: int,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    crypto: CryptoDep,
) -> Response:
    """Decompressed XML text (used by the diff view).

    When the row is encrypted, we Fernet-decrypt the stored per-backup
    password, then decrypt the on-disk blob into plaintext XML — all
    in memory. The decrypted XML never lands on disk. The decrypt event
    is audited so operators can see who read plaintext pfSense config
    (which includes cert keys, VPN PSKs, admin password hashes).

    v0.45.1 — release the DB session before the decrypt to keep the
    pool free during the parse-style hot path.
    """
    row, _ = await _load(db, backup_id)
    filename = row.filename
    snap = _BackupWalkRow(
        id=row.id, started_at=row.started_at, path=row.path,
        compressed=row.compressed, encrypted=row.encrypted,
        encrypt_password_ct=row.encrypt_password_ct,
    )
    await db.close()

    try:
        content = await asyncio.to_thread(_read_for_walk, snap, crypto)
    except _WalkAbortError as abort:
        raise HTTPException(abort.status_code, abort.detail) from abort

    if snap.encrypted:
        async with request.app.state.session_factory() as audit_db:
            audit.record(
                audit_db,
                actor_email=user["email"],
                action="view_decrypted",
                resource="backup",
                resource_id=backup_id,
                details={"filename": filename},
            )
            await audit_db.commit()
    return Response(content=content, media_type="application/xml")


@router.get("/{backup_id}/download", response_model=None)
async def download(
    backup_id: int,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    crypto: CryptoDep,
    raw: bool = False,
) -> StreamingResponse | Response:
    """Download backup bytes.

    For encrypted rows, the default behavior is to serve the decrypted
    XML (same UX as pfSense's post-import decrypt). Pass ``?raw=1`` to
    download the still-encrypted file as-is (for offline inspection or
    round-trip into pfSense's import flow). Decrypted downloads are
    audited; the raw path is recorded too so the log shows which
    operator pulled which file.

    v0.45.1 — release the DB session before the decrypt or stream-out
    so a slow download doesn't hold a pool slot.
    """
    row, path = await _load(db, backup_id)
    filename = row.filename
    snap = _BackupWalkRow(
        id=row.id, started_at=row.started_at, path=row.path,
        compressed=row.compressed, encrypted=row.encrypted,
        encrypt_password_ct=row.encrypt_password_ct,
    )
    await db.close()
    sf = request.app.state.session_factory

    if snap.encrypted and not raw:
        try:
            plaintext = await asyncio.to_thread(_read_for_walk, snap, crypto)
        except _WalkAbortError as abort:
            raise HTTPException(abort.status_code, abort.detail) from abort
        download_name = path.name
        # Strip .gz / .enc-ish suffixes so the user gets a `.xml` they
        # can open directly.
        for suffix in (".gz",):
            if download_name.endswith(suffix):
                download_name = download_name[: -len(suffix)]
        async with sf() as audit_db:
            audit.record(
                audit_db,
                actor_email=user["email"],
                action="download_decrypted",
                resource="backup",
                resource_id=backup_id,
                details={"filename": filename},
            )
            await audit_db.commit()
        return Response(
            content=plaintext,
            media_type="application/xml",
            headers={
                "Content-Disposition": f'attachment; filename="{download_name}"'
            },
        )

    async with sf() as audit_db:
        audit.record(
            audit_db,
            actor_email=user["email"],
            action="download_raw" if snap.encrypted else "download",
            resource="backup",
            resource_id=backup_id,
            details={"filename": filename},
        )
        await audit_db.commit()

    async def body() -> AsyncIterator[bytes]:
        for chunk in await asyncio.to_thread(lambda: list(stream_raw(path))):
            yield chunk

    return StreamingResponse(
        body(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
    )


@router.post("/download-zip")
async def download_zip(
    body: ZipRequest, db: DbSession, user: CurrentUser
) -> StreamingResponse:
    """Stream multiple backups into one zip without buffering in memory (C4).

    ``zip_stream`` writes each file's bytes through a ``zipfile.ZipFile`` into
    a rolling in-memory buffer; each entry is flushed to the client as soon
    as it's encoded, so peak memory is one-file-at-a-time rather than the
    entire zip.
    """
    if not body.ids:
        raise HTTPException(400, "ids must be non-empty")
    if len(body.ids) > 200:
        raise HTTPException(422, "too many ids — max 200 backups per zip")
    paths: list[Path] = []
    for bid in body.ids:
        _, p = await _load(db, bid)
        paths.append(p)
    audit.record(
        db, actor_email=user["email"], action="download_zip",
        resource="backup", resource_id=None,
        details={"ids": body.ids, "count": len(body.ids)},
    )
    await db.commit()
    return StreamingResponse(
        _async_iter(zip_stream(paths)),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="pfsense-backups.zip"'},
    )


async def _async_iter(it) -> AsyncIterator[bytes]:
    """Wrap a sync generator so its blocking I/O stays off the event loop."""
    while True:
        chunk = await asyncio.to_thread(next, it, None)
        if chunk is None:
            return
        yield chunk


class ParsedBackupResponse(BaseModel):
    """Bundled parse result returned by ``GET /api/backups/{id}/parsed``.

    Carries the redacted ``ParsedConfig`` alongside a
    ``positions`` map of anchorId → ``(start_line, end_line)`` so the
    viewer can round-trip between the Structured tab and the Raw XML
    tab without a second round trip. Keys in ``positions`` match the
    DOM ids the frontend emits (``xref-{kind}-{key}``,
    ``xref-{scope}-{key}``, ``field-{section}-{fieldname}``,
    ``section-{section}``).
    """

    config: ParsedConfig
    positions: dict[str, tuple[int, int]]


@router.get("/{backup_id}/parsed", response_model=ParsedBackupResponse)
async def get_parsed(
    backup_id: int,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    crypto: CryptoDep,
) -> ParsedBackupResponse:
    """Structured, redaction-aware projection of the backup's config.xml.

    Encrypted rows get decrypted in memory (same path as ``/content``);
    plaintext never hits disk. Secrets (password hashes, VPN PSKs,
    cert keys, RADIUS shared secrets) are replaced with a fixed
    placeholder in the response so a view here doesn't expose what
    the raw-XML tab would.

    Audited as ``view_decrypted`` for encrypted rows — operators
    reviewing a parsed config are still reading the plaintext config
    via this endpoint.

    v0.22.0 — response wraps the parsed config plus a positions map
    (anchorId → source-line range) so the Structured/Raw XML tab
    switch can jump to the same content without a second request.
    The positions map is built with lxml on the same bytes we already
    parse; adds ~O(tree size) time, no I/O.

    v0.45.1 — release the request-scoped DB session before the
    decrypt+parse so a slow parse doesn't pin a pool slot.
    """
    # Load filename for the audit log before releasing the session;
    # _BackupWalkRow doesn't carry it.
    row, _ = await _load(db, backup_id)
    filename = row.filename
    snap = _BackupWalkRow(
        id=row.id,
        started_at=row.started_at,
        path=row.path,
        compressed=row.compressed,
        encrypted=row.encrypted,
        encrypt_password_ct=row.encrypt_password_ct,
    )
    await db.close()

    try:
        content_bytes = await asyncio.to_thread(_read_for_walk, snap, crypto)
    except _WalkAbortError as abort:
        raise HTTPException(abort.status_code, abort.detail) from abort
    if isinstance(content_bytes, str):
        content_bytes = content_bytes.encode("utf-8")

    if snap.encrypted:
        async with request.app.state.session_factory() as audit_db:
            audit.record(
                audit_db,
                actor_email=user["email"],
                action="view_decrypted",
                resource="backup",
                resource_id=backup_id,
                details={"filename": filename, "via": "parsed"},
            )
            await audit_db.commit()

    try:
        parsed = await asyncio.to_thread(parse_pfsense_xml, content_bytes)
    except PfSenseParseError as exc:
        raise HTTPException(422, str(exc)) from exc
    # Pass ``parsed`` so firewall + NAT rule anchors pair 1:1 with the
    # parser's synthesized ``r.key`` (tracker-less rules get a hash
    # fallback that the frontend also emits via ``rowAnchorId``).
    positions = await asyncio.to_thread(build_positions, content_bytes, parsed)
    return ParsedBackupResponse(config=parsed, positions=positions)


@router.get("/diff/pair/parsed", response_model=ConfigDiff)
async def diff_pair_parsed(
    a: int,
    b: int,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    crypto: CryptoDep,
) -> ConfigDiff:
    """Semantic diff between two parsed configs.

    Decrypts both sides in memory, parses each, then runs the
    structured diff engine. Single audit entry per pair when either
    side is encrypted.

    v0.45.1 — release the request-scoped DB session before the
    heavy decrypt+parse+diff. The scrubber fires one of these per
    focused-backup change; holding a pool slot through 100ms–1s+
    of CPU/IO exhausts the pool at <60 concurrent requests.
    """
    a_snap = await _load_and_snapshot(db, a)
    b_snap = await _load_and_snapshot(db, b)
    await db.close()

    def _read_both() -> tuple[bytes | str, bytes | str]:
        return (
            _read_for_walk(a_snap, crypto),
            _read_for_walk(b_snap, crypto),
        )

    try:
        a_bytes, b_bytes = await asyncio.to_thread(_read_both)
        a_parsed = await asyncio.to_thread(parse_pfsense_xml, a_bytes)
        b_parsed = await asyncio.to_thread(parse_pfsense_xml, b_bytes)
    except _WalkAbortError as abort:
        raise HTTPException(abort.status_code, abort.detail) from abort
    except PfSenseParseError as exc:
        raise HTTPException(422, str(exc)) from exc
    result = await asyncio.to_thread(diff_configs, a_parsed, b_parsed)

    if a_snap.encrypted or b_snap.encrypted:
        async with request.app.state.session_factory() as audit_db:
            audit.record(
                audit_db,
                actor_email=user["email"],
                action="view_decrypted",
                resource="backup_diff",
                resource_id=None,
                details={"a": a_snap.id, "b": b_snap.id, "via": "parsed"},
            )
            await audit_db.commit()
    return result


@router.get("/diff/pair")
async def diff_pair(
    a: int,
    b: int,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    crypto: CryptoDep,
) -> dict[str, Any]:
    """Return both backups' decompressed XML content for a side-by-side diff view.

    Encrypted rows get decrypted in memory using their per-backup
    password so the diff view sees plaintext XML on either side. The
    decrypt event is audited so operators can see who read plaintext
    pfSense config via the diff path.

    v0.45.1 — snapshot row metadata, release the DB session, then
    do the file reads + decrypts on a worker thread. Audit row goes
    through a fresh session if either side was encrypted.
    """
    # Snapshot the full row so we have filename for the response
    # without holding a session through the file reads. The snapshot
    # struct only carries fields ``_read_for_walk`` needs, so capture
    # filename separately.
    a_row, _ = await _load(db, a)
    b_row, _ = await _load(db, b)
    a_filename, a_started_at = a_row.filename, a_row.started_at
    b_filename, b_started_at = b_row.filename, b_row.started_at
    a_snap = _BackupWalkRow(
        id=a_row.id, started_at=a_started_at, path=a_row.path,
        compressed=a_row.compressed, encrypted=a_row.encrypted,
        encrypt_password_ct=a_row.encrypt_password_ct,
    )
    b_snap = _BackupWalkRow(
        id=b_row.id, started_at=b_started_at, path=b_row.path,
        compressed=b_row.compressed, encrypted=b_row.encrypted,
        encrypt_password_ct=b_row.encrypt_password_ct,
    )
    await db.close()

    def _read_both() -> tuple[bytes | str, bytes | str]:
        return (
            _read_for_walk(a_snap, crypto),
            _read_for_walk(b_snap, crypto),
        )

    def _as_str(v: bytes | str) -> str:
        return v.decode("utf-8", errors="replace") if isinstance(v, bytes) else v

    try:
        a_bytes, b_bytes = await asyncio.to_thread(_read_both)
    except _WalkAbortError as abort:
        raise HTTPException(abort.status_code, abort.detail) from abort
    a_content = _as_str(a_bytes)
    b_content = _as_str(b_bytes)

    if a_snap.encrypted or b_snap.encrypted:
        async with request.app.state.session_factory() as audit_db:
            audit.record(
                audit_db,
                actor_email=user["email"],
                action="view_decrypted",
                resource="backup_diff",
                resource_id=None,
                details={"a": a_snap.id, "b": b_snap.id},
            )
            await audit_db.commit()
    return {
        "a": {
            "id": a_snap.id,
            "filename": a_filename,
            "started_at": a_started_at.isoformat(),
            "content": a_content,
        },
        "b": {
            "id": b_snap.id,
            "filename": b_filename,
            "started_at": b_started_at.isoformat(),
            "content": b_content,
        },
    }


# --------------------------------------------------------------------- #
# v0.37.0 — precomputed "+N since first" summaries + full "vs first"
# diff view, backed by the ``backup_diff`` table. Writer lives in the
# worker (``_compute_and_persist_diffs``); readers below handle cache
# hits, lazy recompute on staleness (first backup pruned → base NULL),
# and on-demand backfill for backups that predate v0.37.0.
# --------------------------------------------------------------------- #


class DiffSummary(BaseModel):
    added: int
    removed: int
    modified: int


class DiffSummaryResponse(BaseModel):
    backup_id: int
    # Each side is ``None`` when there's no backup to diff against
    # (e.g. this IS the first backup for its instance).
    vs_previous: DiffSummary | None = None
    vs_first: DiffSummary | None = None
    first_backup_id: int | None = None
    first_backup_started_at: str | None = None


async def _find_base(
    db: AsyncSession, backup: Backup, kind: str
) -> Backup | None:
    """Resolve the base backup for a given ``(backup, kind)``. Returns
    None when no base exists — first-ever backup for 'previous', or
    an instance with only one successful backup for 'first'."""
    if kind == "previous":
        stmt = (
            select(Backup)
            .where(Backup.instance_id == backup.instance_id)
            .where(Backup.success.is_(True))
            .where(Backup.id != backup.id)
            .where(Backup.started_at < backup.started_at)
            .order_by(Backup.started_at.desc())
            .limit(1)
        )
    elif kind == "first":
        stmt = (
            select(Backup)
            .where(Backup.instance_id == backup.instance_id)
            .where(Backup.success.is_(True))
            .where(Backup.id != backup.id)
            .order_by(Backup.started_at.asc())
            .limit(1)
        )
    else:
        return None
    return (await db.execute(stmt)).scalar_one_or_none()


async def _recompute_diff_row(
    session_factory: Any,
    backup_snap: _BackupWalkRow,
    base_snap: _BackupWalkRow,
    kind: str,
    crypto: Any,
) -> BackupDiff | None:
    """Lazy recompute path: missing row OR stale (base pruned). Reads
    both backups from disk, diffs them, upserts the row. Returns the
    freshly-inserted ``BackupDiff`` or None if computation failed
    (base missing on disk, XML malformed).

    v0.45.1 — operates on snapshots; the caller must have already
    released its own DB session before invoking this. The heavy
    file read + diff happens with no connection held; only the brief
    upsert acquires a pool slot via ``session_factory``.
    """
    def _read() -> tuple[bytes | None, bytes | None]:
        new_b = read_backup_bytes(
            _row_path(backup_snap.path),
            encrypted=backup_snap.encrypted,
            encrypt_password_ct=backup_snap.encrypt_password_ct,
            crypto=crypto,
        )
        base_b = read_backup_bytes(
            _row_path(base_snap.path),
            encrypted=base_snap.encrypted,
            encrypt_password_ct=base_snap.encrypt_password_ct,
            crypto=crypto,
        )
        return new_b, base_b

    new_bytes, base_bytes = await asyncio.to_thread(_read)
    if new_bytes is None or base_bytes is None:
        return None
    diff = await asyncio.to_thread(compute_diff, new_bytes, base_bytes)
    if diff is None:
        return None
    added, removed, modified = summarise_diff(diff)
    blob = encode_diff(diff)
    async with session_factory() as write_db:
        # Delete any existing (stale) row, then insert fresh.
        existing = await write_db.get(BackupDiff, (backup_snap.id, kind))
        if existing is not None:
            await write_db.delete(existing)
            await write_db.flush()
        row = BackupDiff(
            backup_id=backup_snap.id,
            kind=kind,
            base_backup_id=base_snap.id,
            added_count=added,
            removed_count=removed,
            modified_count=modified,
            full_diff_gz=blob,
        )
        write_db.add(row)
        await write_db.commit()
        # Session factory uses ``expire_on_commit=False`` so the
        # ORM attributes stay populated after the session closes —
        # callers can read primitive fields on the returned row.
    return row


def _snap(backup: Backup) -> _BackupWalkRow:
    """Pluck a thread-safe snapshot out of a live ORM row."""
    return _BackupWalkRow(
        id=backup.id,
        started_at=backup.started_at,
        path=backup.path,
        compressed=backup.compressed,
        encrypted=backup.encrypted,
        encrypt_password_ct=backup.encrypt_password_ct,
    )


def _is_fresh(cached: BackupDiff | None, base: Backup | None) -> bool:
    """A cached ``backup_diff`` row is fresh when it points at the
    currently-canonical base for its kind. Stale = base was pruned
    or replaced (e.g. retention removed the first-ever backup)."""
    return (
        cached is not None
        and base is not None
        and cached.base_backup_id == base.id
    )


@router.get("/{backup_id}/diff-summary", response_model=DiffSummaryResponse)
async def backup_diff_summary(
    backup_id: int,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    crypto: CryptoDep,
) -> DiffSummaryResponse:
    """Return the "+N since previous" + "+N since first" count
    rollups for a backup. Hits the ``backup_diff`` table; on miss or
    stale (first backup pruned) it recomputes + upserts lazily. Safe
    to call on backups that predate v0.37.0 — they simply pay the
    full diff cost on first access and are cached afterwards.

    v0.45.1 — cache lookups + base resolution run on the
    request-scoped session, which is then closed BEFORE any heavy
    recompute. The recompute helper handles its own writeback via
    a fresh session, so a slow backfill no longer pins a pool slot.
    """
    backup = await db.get(Backup, backup_id)
    if backup is None:
        raise HTTPException(404, "backup not found")

    backup_encrypted = backup.encrypted
    backup_snap = _snap(backup)

    prev_base = await _find_base(db, backup, "previous")
    first_base = await _find_base(db, backup, "first")
    cached_prev = await db.get(BackupDiff, (backup_id, "previous"))
    cached_first = await db.get(BackupDiff, (backup_id, "first"))

    prev_fresh = _is_fresh(cached_prev, prev_base)
    first_fresh = _is_fresh(cached_first, first_base)

    # Pull primitives out of ORM rows BEFORE closing the session;
    # detached-instance access for these primitives would still
    # technically work (``expire_on_commit=False``), but explicit
    # extraction here makes the post-close code obviously safe.
    first_backup_id_out: int | None = first_base.id if first_base else None
    first_backup_started_at_iso: str | None = (
        first_base.started_at.isoformat() if first_base else None
    )
    cached_prev_counts: tuple[int, int, int] | None = (
        (cached_prev.added_count, cached_prev.removed_count, cached_prev.modified_count)
        if prev_fresh and cached_prev is not None
        else None
    )
    cached_first_counts: tuple[int, int, int] | None = (
        (cached_first.added_count, cached_first.removed_count, cached_first.modified_count)
        if first_fresh and cached_first is not None
        else None
    )

    # Snapshot base rows only for kinds that may need recompute.
    prev_base_snap = (
        _snap(prev_base) if prev_base is not None and not prev_fresh else None
    )
    first_base_snap = (
        _snap(first_base) if first_base is not None and not first_fresh else None
    )

    await db.close()

    sf = request.app.state.session_factory
    if cached_prev_counts is None and prev_base_snap is not None:
        row = await _recompute_diff_row(
            sf, backup_snap, prev_base_snap, "previous", crypto
        )
        if row is not None:
            cached_prev_counts = (
                row.added_count, row.removed_count, row.modified_count,
            )
    if cached_first_counts is None and first_base_snap is not None:
        row = await _recompute_diff_row(
            sf, backup_snap, first_base_snap, "first", crypto
        )
        if row is not None:
            cached_first_counts = (
                row.added_count, row.removed_count, row.modified_count,
            )

    # Encrypted backups can't be diffed without decryption. Preserve
    # the v0.37.0 semantic: any diff returned + encrypted backup =>
    # log a view_decrypted entry. Fresh session for the write.
    if (cached_prev_counts is not None or cached_first_counts is not None) and backup_encrypted:
        async with sf() as audit_db:
            audit.record(
                audit_db,
                actor_email=user["email"],
                action="view_decrypted",
                resource="backup_diff_summary",
                resource_id=str(backup_id),
            )
            await audit_db.commit()

    return DiffSummaryResponse(
        backup_id=backup_id,
        vs_previous=(
            DiffSummary(
                added=cached_prev_counts[0],
                removed=cached_prev_counts[1],
                modified=cached_prev_counts[2],
            )
            if cached_prev_counts is not None
            else None
        ),
        vs_first=(
            DiffSummary(
                added=cached_first_counts[0],
                removed=cached_first_counts[1],
                modified=cached_first_counts[2],
            )
            if cached_first_counts is not None
            else None
        ),
        first_backup_id=first_backup_id_out,
        first_backup_started_at=first_backup_started_at_iso,
    )


@router.get("/{backup_id}/diff-vs-first/parsed")
async def backup_diff_vs_first_parsed(
    backup_id: int,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    crypto: CryptoDep,
) -> dict[str, Any]:
    """Full ``ConfigDiff`` JSON between this backup and the oldest-
    still-on-disk backup for the same instance. Served from the
    cached ``full_diff_gz`` blob whenever available; falls through to
    recompute on miss / stale. Returns 404 when there's no first
    backup to diff against (single-backup instance), 409 when the
    diff cannot be computed (XML malformed, base file missing).

    v0.45.1 — cache lookup runs on the request-scoped session, which
    is then closed before any recompute.
    """
    backup = await db.get(Backup, backup_id)
    if backup is None:
        raise HTTPException(404, "backup not found")

    backup_encrypted = backup.encrypted
    backup_snap = _snap(backup)

    first_base = await _find_base(db, backup, "first")
    cached_first = await db.get(BackupDiff, (backup_id, "first"))
    fresh = _is_fresh(cached_first, first_base)

    cached_blob: bytes | None = (
        cached_first.full_diff_gz if fresh and cached_first is not None else None
    )
    first_base_snap = (
        _snap(first_base) if first_base is not None and not fresh else None
    )
    # "no first base exists" must be distinguishable from "compute
    # failed" further down; capture the existence-of-base bit now.
    has_first_base = first_base is not None

    await db.close()

    sf = request.app.state.session_factory
    diff_blob: bytes
    if cached_blob is not None:
        diff_blob = cached_blob
    elif first_base_snap is not None:
        row = await _recompute_diff_row(
            sf, backup_snap, first_base_snap, "first", crypto
        )
        if row is None:
            raise HTTPException(
                409,
                "could not compute diff against first backup "
                "(base file missing or XML malformed)",
            )
        diff_blob = row.full_diff_gz
    elif not has_first_base:
        raise HTTPException(
            404,
            "no earlier backup to diff against — this is the first "
            "successful backup for its instance",
        )
    else:
        # has_first_base=True but no snapshot ⇒ fresh cache existed
        # but with no blob. Defensive — shouldn't happen in practice.
        raise HTTPException(500, "diff blob missing for fresh cache row")

    if backup_encrypted:
        async with sf() as audit_db:
            audit.record(
                audit_db,
                actor_email=user["email"],
                action="view_decrypted",
                resource="backup_diff_vs_first",
                resource_id=str(backup_id),
            )
            await audit_db.commit()

    return decode_diff(diff_blob)


# --------------------------------------------------------------------- #
# v0.24.0 — per-anchor blame: history of a single row / field across
# every successful backup of an instance.
# --------------------------------------------------------------------- #


class AnchorHistoryChange(BaseModel):
    """One entry on the blame timeline for a single anchor.

    ``is_change`` is True when this backup's value differs from the
    previous backup's value — both the appearance (None → non-None)
    and the disappearance (non-None → None) of the anchor count as
    changes. The blame drawer emphasises change entries while still
    listing unchanged backups so the operator can see the gap
    between changes.
    """

    backup_id: int
    started_at: str
    value: Any
    is_change: bool


class AnchorHistoryResponse(BaseModel):
    anchor: str
    instance_id: int
    entries: list[AnchorHistoryChange]
    # True when the response came from the indexed ``anchor_event``
    # table (v0.40.0+). False when the instance predates the v0.40.0
    # backfill and we fell back to the per-request snapshot walk.
    # Exposed so smoke-tests can assert the fast path kicked in.
    indexed: bool = False


class _WalkAbortError(Exception):
    """Plain-Python exception used to carry an ``HTTPException`` across
    ``asyncio.to_thread`` in the anchor-history walker. Raising
    ``HTTPException`` directly inside ``to_thread`` happens to work on
    CPython today but is undocumented — using a domain exception and
    translating in the outer coroutine keeps the boundary explicit."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _BackupWalkRow(BaseModel):
    """Plain snapshot of a ``Backup`` row — safe to hand to a worker
    thread (unlike the live ORM instance, which can lazy-load attrs
    on access and is not thread-safe when accessed off the event
    loop)."""

    model_config = {"arbitrary_types_allowed": True}

    id: int
    started_at: datetime
    path: str
    compressed: bool
    encrypted: bool
    encrypt_password_ct: bytes | None


def _row_path(raw_path: str) -> Path:
    p = Path(raw_path)
    return p if p.is_absolute() else BACKUPS_DIR / p


def _read_for_walk(row: _BackupWalkRow, crypto: Any) -> bytes | str:
    """Read a backup file (handles .gz + decryption) using a plain
    snapshot (``_BackupWalkRow``) instead of an ORM instance — safe
    to call from inside ``asyncio.to_thread``."""
    import gzip

    path = _row_path(row.path)
    if path.suffix == ".gz" or row.compressed:
        with gzip.open(path, "rb") as gz:
            raw = gz.read()
    else:
        raw = path.read_bytes()
    if not row.encrypted or not looks_encrypted(raw):
        return raw
    if not row.encrypt_password_ct:
        # Raises ``_WalkAbortError`` instead of HTTPException because
        # this function is called from inside ``asyncio.to_thread``.
        # The outer coroutine catches ``_WalkAbortError`` and
        # translates to a real HTTPException in a normal async frame.
        raise _WalkAbortError(
            status.HTTP_409_CONFLICT,
            "cannot decrypt backup: no per-row password stored. "
            "Download the raw encrypted file and decrypt offline.",
        )
    try:
        password = crypto.decrypt(row.encrypt_password_ct)
    except Exception as exc:
        raise _WalkAbortError(
            status.HTTP_409_CONFLICT,
            f"cannot decrypt backup password: {exc}",
        ) from exc
    try:
        return decrypt_pfsense_backup(raw, password)
    except PfSenseCryptoError as exc:
        raise _WalkAbortError(
            status.HTTP_409_CONFLICT,
            f"cannot decrypt backup — password missing or KDF mismatch ({exc})",
        ) from exc


@router.get(
    "/instance/{instance_id}/anchor-history",
    response_model=AnchorHistoryResponse,
)
async def instance_anchor_history(
    instance_id: int,
    anchor: str,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    crypto: CryptoDep,
) -> AnchorHistoryResponse:
    """Per-anchor blame timeline for a pfSense instance.

    v0.40.0 fast path: if the instance has been indexed
    (``Instance.anchor_events_backfilled_at`` is non-null), serve
    the timeline directly from the ``anchor_event`` table — one
    SELECT, no decrypt / parse at request time.

    Legacy fallback (pre-v0.40.0 instances, until ``worker
    reindex-anchor-events`` has run): walks every successful
    backup, decrypts + parses each, resolves ``anchor`` to the
    value it points at in that backup, records transitions. Same
    response shape so the frontend handles both transparently.

    The legacy path keeps its connection-discipline (snapshot rows,
    close session before entering the parse thread), its LRU cache,
    and its ``view_decrypted`` audit log. The indexed path bypasses
    all three — no decryption happens, no long-held connection.
    """
    # Load instance + its successful backups in ascending order.
    inst_row = (
        await db.execute(select(Instance).where(Instance.id == instance_id))
    ).scalar_one_or_none()
    if inst_row is None:
        raise HTTPException(status_code=404, detail="instance not found")

    # Fast path — indexed query against ``anchor_event``.
    if inst_row.anchor_events_backfilled_at is not None:
        import json as _json

        # Window-dedupe on ``(anchor_id, backup_id)`` so a firewall
        # rule that was both edited and reordered in the same backup
        # surfaces as ONE timeline entry rather than two rows with
        # the same backup_id (React key collision + visual duplicate
        # in the drawer). Kind priority prefers ``modified`` over
        # ``reordered`` when both exist for the same backup — the
        # operator-facing summary shows what substantively changed.
        dedupe_subq = (
            select(
                AnchorEvent.id.label("event_id"),
                AnchorEvent.backup_id,
                AnchorEvent.occurred_at,
                AnchorEvent.kind,
                AnchorEvent.value_json,
                func.row_number()
                .over(
                    partition_by=(
                        AnchorEvent.anchor_id,
                        AnchorEvent.backup_id,
                    ),
                    order_by=(
                        _anchor_event_kind_priority().asc(),
                        AnchorEvent.id.desc(),
                    ),
                )
                .label("rn"),
            )
            .where(AnchorEvent.instance_id == instance_id)
            .where(AnchorEvent.anchor_id == anchor)
            .subquery()
        )
        event_rows_raw = (
            await db.execute(
                select(
                    dedupe_subq.c.backup_id,
                    dedupe_subq.c.occurred_at,
                    dedupe_subq.c.kind,
                    dedupe_subq.c.value_json,
                ).where(dedupe_subq.c.rn == 1).order_by(dedupe_subq.c.occurred_at.asc())
            )
        ).all()
        entries = [
            AnchorHistoryChange(
                backup_id=int(backup_id),
                started_at=occurred_at.isoformat(),
                value=(_json.loads(value_json) if value_json is not None else None),
                # Every persisted event IS a change — the projector
                # only emits on transitions. Flag stays True so the
                # existing drawer "emphasise changes" rendering works
                # unchanged.
                is_change=True,
            )
            for backup_id, occurred_at, _kind, value_json in event_rows_raw
        ]
        # Audit even on the indexed path — ``value_json`` in
        # ``anchor_event`` was derived from decrypted backup content
        # at ingestion time, so operators with a compliance mandate
        # still need to see "who viewed what." No runtime decryption
        # happens here (the label changes from ``view_decrypted`` to
        # ``view_anchor_history`` to reflect that).
        audit.record(
            db,
            actor_email=user["email"],
            action="view_anchor_history",
            resource="anchor_history",
            resource_id=str(instance_id),
            details={"anchor": anchor, "entries": len(entries)},
        )
        await db.commit()
        return AnchorHistoryResponse(
            anchor=anchor,
            instance_id=instance_id,
            entries=entries,
            indexed=True,
        )

    rows = (
        await db.execute(
            select(Backup)
            .where(Backup.instance_id == instance_id)
            .where(Backup.success.is_(True))
            .order_by(Backup.started_at.asc())
        )
    ).scalars().all()

    # Snapshot everything we need from the ORM BEFORE releasing the
    # session. Subsequent code treats ``snapshots`` as plain data,
    # safe to consume from a worker thread.
    snapshots = [
        _BackupWalkRow(
            id=r.id,
            started_at=r.started_at,
            path=r.path,
            compressed=r.compressed,
            encrypted=r.encrypted,
            encrypt_password_ct=r.encrypt_password_ct,
        )
        for r in rows
    ]

    # Release the pool connection immediately — the parse loop below
    # can be slow and would otherwise starve concurrent callers.
    await db.close()

    any_encrypted = any(s.encrypted for s in snapshots)

    def _gather() -> list[AnchorHistoryChange]:
        out: list[AnchorHistoryChange] = []
        previous_value: Any = _MISSING
        for s in snapshots:
            raw_bytes: bytes | str
            if s.encrypted:
                # ``_read_for_walk`` raises ``_WalkAbortError`` directly
                # so it can carry status+detail across the
                # ``asyncio.to_thread`` boundary without an HTTPException
                # round-trip. Caught by the outer coroutine below.
                raw_bytes = _read_for_walk(s, crypto)
            else:
                raw_bytes = read_content(_row_path(s.path))
            try:
                parsed = parse_pfsense_xml(raw_bytes)
            except PfSenseParseError as exc:
                raise _WalkAbortError(
                    422, f"backup id={s.id} could not be parsed: {exc}"
                ) from exc
            value = resolve_anchor_value(parsed, anchor)
            is_change = previous_value is _MISSING or value != previous_value
            out.append(
                AnchorHistoryChange(
                    backup_id=s.id,
                    started_at=s.started_at.isoformat(),
                    value=value,
                    is_change=is_change,
                )
            )
            previous_value = value
        return out

    # LRU cache keyed ``(instance_id, anchor)``. The cached result
    # includes every snapshot walked, so any new backup for this
    # instance invalidates the entry (handled by the
    # ``_anchor_history_invalidator`` background task in ``app.py``).
    # Cache miss pays the full walk + parse cost; hit short-circuits.
    cache = getattr(request.app.state, "anchor_history_cache", None)
    cache_key = (instance_id, anchor)
    cached = cache.get(cache_key) if cache is not None else None
    entries: list[AnchorHistoryChange]
    if cached is not None:
        entries = cached
    else:
        try:
            entries = await asyncio.to_thread(_gather)
        except _WalkAbortError as abort:
            raise HTTPException(abort.status_code, abort.detail) from abort
        if cache is not None:
            cache[cache_key] = entries

    if any_encrypted:
        # Fresh session from the factory — the original ``db`` was
        # closed above. ``async with`` returns the connection to the
        # pool when the audit commit completes.
        session_factory = request.app.state.session_factory
        async with session_factory() as audit_session:
            audit.record(
                audit_session,
                actor_email=user["email"],
                action="view_decrypted",
                resource="anchor_history",
                resource_id=instance_id,
                details={"anchor": anchor, "backups": len(entries)},
            )
            await audit_session.commit()

    return AnchorHistoryResponse(
        anchor=anchor,
        instance_id=instance_id,
        entries=entries,
        indexed=False,
    )


# Sentinel so the "first iteration is always a change" pattern works
# even when the value happens to be ``None``.
_MISSING = object()


def _anchor_event_kind_priority():  # type: ignore[no-untyped-def]
    """SQLAlchemy CASE expression that ranks event kinds by
    informativeness. Used as a secondary ORDER BY clause so that
    when two events share an ``occurred_at`` (e.g. a firewall rule
    both edited and repositioned in the same backup produces one
    ``modified`` + one ``reordered`` event), the ``modified`` event
    wins ties — operators reading blame want to know WHAT changed
    before they know that something moved.

    Lower number = higher priority (use with ``.asc()``).
    """
    return case(
        (AnchorEvent.kind == "modified", 1),
        (AnchorEvent.kind == "added", 2),
        (AnchorEvent.kind == "removed", 3),
        (AnchorEvent.kind == "reordered", 4),
        else_=5,
    )


# --------------------------------------------------------------------- #
# v0.40.0 — indexed surfaces that ride the ``anchor_event`` table.
# --------------------------------------------------------------------- #


class AnchorBlameSummaryEntry(BaseModel):
    """Most-recent event for a single anchor, as of a given backup.

    Feeds the inline hover-tooltip on Structured + Raw XML views —
    the frontend prefetches the whole map for a page view and the
    tooltip renders zero-latency on hover.
    """

    backup_id: int
    occurred_at: str
    kind: str


class AnchorBlameSummaryResponse(BaseModel):
    as_of_backup_id: int
    anchors: dict[str, AnchorBlameSummaryEntry]
    # False for instances that haven't been backfilled yet —
    # frontend suppresses the tooltip surface in that case (no
    # data to show). Same indexed/legacy distinction as
    # ``AnchorHistoryResponse``.
    indexed: bool


@router.get(
    "/instance/{instance_id}/anchor-blame-summary",
    response_model=AnchorBlameSummaryResponse,
)
async def instance_anchor_blame_summary(
    instance_id: int,
    db: DbSession,
    user: CurrentUser,
    as_of_backup_id: int | None = Query(default=None),
) -> AnchorBlameSummaryResponse:
    """Latest ``AnchorEvent`` per ``anchor_id`` for an instance, at
    or before ``as_of_backup_id`` (defaults to the instance's newest
    successful backup).

    Returns a map keyed on ``anchor_id``; payload is small (one
    entry per changed anchor, typically ≤few hundred), so the
    browser caches the whole thing for the page lifetime and the
    tooltip never makes a per-hover request.
    """
    inst = (
        await db.execute(select(Instance).where(Instance.id == instance_id))
    ).scalar_one_or_none()
    if inst is None:
        raise HTTPException(status_code=404, detail="instance not found")

    # Resolve ``as_of_backup_id`` → ``as_of_started_at``. Default to
    # the latest successful backup for this instance.
    if as_of_backup_id is None:
        row = (
            await db.execute(
                select(Backup.id, Backup.started_at)
                .where(Backup.instance_id == instance_id)
                .where(Backup.success.is_(True))
                .order_by(Backup.started_at.desc())
                .limit(1)
            )
        ).first()
        if row is None:
            return AnchorBlameSummaryResponse(
                as_of_backup_id=0,
                anchors={},
                indexed=inst.anchor_events_backfilled_at is not None,
            )
        as_of_backup_id_resolved = int(row[0])
        as_of_started_at = row[1]
    else:
        row = (
            await db.execute(
                select(Backup.id, Backup.started_at)
                .where(Backup.id == as_of_backup_id)
                .where(Backup.instance_id == instance_id)
            )
        ).first()
        if row is None:
            raise HTTPException(
                status_code=404, detail="backup not found for this instance"
            )
        as_of_backup_id_resolved = int(row[0])
        as_of_started_at = row[1]

    if inst.anchor_events_backfilled_at is None:
        # Pre-v0.40.0 instance — no index, no tooltip data. Frontend
        # interprets ``indexed=False`` as "hide the tooltip surface."
        return AnchorBlameSummaryResponse(
            as_of_backup_id=as_of_backup_id_resolved,
            anchors={},
            indexed=False,
        )

    # Window-function query: latest row per anchor at-or-before the
    # cut-off. SQLite 3.25+ supports ROW_NUMBER() OVER (...).
    subq = (
        select(
            AnchorEvent.anchor_id,
            AnchorEvent.backup_id,
            AnchorEvent.occurred_at,
            AnchorEvent.kind,
            func.row_number()
            .over(
                partition_by=AnchorEvent.anchor_id,
                # Tie-break chain: latest ``occurred_at`` wins; on
                # identical timestamps (modified + reordered for the
                # same backup), the kind priority — ``modified`` >
                # ``added`` > ``removed`` > ``reordered`` — decides
                # which event surfaces in the tooltip. Without this
                # the projector's emission order would always surface
                # ``reordered``, which carries less signal than the
                # field-level edit.
                order_by=(
                    AnchorEvent.occurred_at.desc(),
                    _anchor_event_kind_priority().asc(),
                    AnchorEvent.id.desc(),
                ),
            )
            .label("rn"),
        )
        .where(AnchorEvent.instance_id == instance_id)
        .where(AnchorEvent.occurred_at <= as_of_started_at)
        .subquery()
    )
    result = await db.execute(
        select(subq.c.anchor_id, subq.c.backup_id, subq.c.occurred_at, subq.c.kind)
        .where(subq.c.rn == 1)
    )
    anchors: dict[str, AnchorBlameSummaryEntry] = {}
    for anchor_id, backup_id, occurred_at, kind in result:
        anchors[anchor_id] = AnchorBlameSummaryEntry(
            backup_id=int(backup_id),
            occurred_at=occurred_at.isoformat(),
            kind=kind,
        )

    return AnchorBlameSummaryResponse(
        as_of_backup_id=as_of_backup_id_resolved,
        anchors=anchors,
        indexed=True,
    )


class CumulativeChangeRow(BaseModel):
    anchor_id: str
    section: str | None
    label: str
    first_seen_at: str
    last_change_at: str
    change_count: int
    latest_kind: str
    original_value: Any
    current_value: Any


class CumulativeChangesResponse(BaseModel):
    since_backup_id: int
    until_backup_id: int
    rows: list[CumulativeChangeRow]
    indexed: bool


@router.get(
    "/instance/{instance_id}/cumulative-changes",
    response_model=CumulativeChangesResponse,
)
async def instance_cumulative_changes(
    instance_id: int,
    db: DbSession,
    user: CurrentUser,
    since_backup_id: int | None = Query(default=None),
    until_backup_id: int | None = Query(default=None),
) -> CumulativeChangesResponse:
    """Every anchor that has ≥1 event in the backup-range window,
    collapsed to "original → current" one row per anchor, sorted
    by most-recent change first.

    Defaults: ``since`` = oldest retained backup, ``until`` =
    newest. Operators narrow the window via the range picker in
    the UI.
    """
    inst = (
        await db.execute(select(Instance).where(Instance.id == instance_id))
    ).scalar_one_or_none()
    if inst is None:
        raise HTTPException(status_code=404, detail="instance not found")

    # Resolve the window endpoints to backup ids + started_at.
    since_row = None
    until_row = None
    if since_backup_id is not None:
        since_row = (
            await db.execute(
                select(Backup.id, Backup.started_at)
                .where(Backup.id == since_backup_id)
                .where(Backup.instance_id == instance_id)
            )
        ).first()
        if since_row is None:
            raise HTTPException(
                status_code=404, detail="since-backup not found for this instance"
            )
    else:
        since_row = (
            await db.execute(
                select(Backup.id, Backup.started_at)
                .where(Backup.instance_id == instance_id)
                .where(Backup.success.is_(True))
                .order_by(Backup.started_at.asc())
                .limit(1)
            )
        ).first()
    if until_backup_id is not None:
        until_row = (
            await db.execute(
                select(Backup.id, Backup.started_at)
                .where(Backup.id == until_backup_id)
                .where(Backup.instance_id == instance_id)
            )
        ).first()
        if until_row is None:
            raise HTTPException(
                status_code=404, detail="until-backup not found for this instance"
            )
    else:
        until_row = (
            await db.execute(
                select(Backup.id, Backup.started_at)
                .where(Backup.instance_id == instance_id)
                .where(Backup.success.is_(True))
                .order_by(Backup.started_at.desc())
                .limit(1)
            )
        ).first()

    if since_row is None or until_row is None:
        return CumulativeChangesResponse(
            since_backup_id=0,
            until_backup_id=0,
            rows=[],
            indexed=inst.anchor_events_backfilled_at is not None,
        )

    since_id = int(since_row[0])
    since_at = since_row[1]
    until_id = int(until_row[0])
    until_at = until_row[1]

    if inst.anchor_events_backfilled_at is None:
        return CumulativeChangesResponse(
            since_backup_id=since_id,
            until_backup_id=until_id,
            rows=[],
            indexed=False,
        )

    if since_at > until_at:
        since_at, until_at = until_at, since_at
        since_id, until_id = until_id, since_id

    # Window over anchor_event per anchor_id: smallest + largest
    # occurred_at in the window; row at smallest is ``original``, row
    # at largest is ``current``. One CTE with ROW_NUMBER() on both
    # directions gives us both in a single scan.
    from sqlalchemy import and_
    from sqlalchemy.orm import aliased

    # Pre-dedupe: when two events exist for the same ``(anchor_id,
    # backup_id)`` (modified + reordered in one backup), collapse to
    # the higher-signal event before running the first/last window.
    # Without this the window could pick the ``reordered`` event as
    # ``last`` and the ``modified`` event as ``first`` (both at the
    # same timestamp), stitching a misleading original→current pair.
    dedupe_by_backup = (
        select(
            AnchorEvent.id,
            AnchorEvent.anchor_id,
            AnchorEvent.backup_id,
            AnchorEvent.occurred_at,
            AnchorEvent.kind,
            AnchorEvent.value_json,
            func.row_number()
            .over(
                partition_by=(AnchorEvent.anchor_id, AnchorEvent.backup_id),
                order_by=(
                    _anchor_event_kind_priority().asc(),
                    AnchorEvent.id.desc(),
                ),
            )
            .label("rn_dedupe"),
        )
        .where(AnchorEvent.instance_id == instance_id)
        .where(AnchorEvent.occurred_at >= since_at)
        .where(AnchorEvent.occurred_at <= until_at)
        .subquery()
    )
    windowed = (
        select(
            dedupe_by_backup.c.id,
            dedupe_by_backup.c.anchor_id,
            dedupe_by_backup.c.backup_id,
            dedupe_by_backup.c.occurred_at,
            dedupe_by_backup.c.kind,
            dedupe_by_backup.c.value_json,
            func.row_number()
            .over(
                partition_by=dedupe_by_backup.c.anchor_id,
                # Tie-break on ``id`` so rn_first and rn_last agree on
                # "which physical row is first/last" when two events
                # share an ``occurred_at``. Without this, the self-join
                # can stitch ``first.value_json`` from one event and
                # ``last.value_json`` from another at the same
                # timestamp, producing an internally-inconsistent row.
                order_by=(
                    dedupe_by_backup.c.occurred_at.asc(),
                    dedupe_by_backup.c.id.asc(),
                ),
            )
            .label("rn_first"),
            func.row_number()
            .over(
                partition_by=dedupe_by_backup.c.anchor_id,
                order_by=(
                    dedupe_by_backup.c.occurred_at.desc(),
                    dedupe_by_backup.c.id.desc(),
                ),
            )
            .label("rn_last"),
        )
        .where(dedupe_by_backup.c.rn_dedupe == 1)
        .subquery()
    )
    first_in_win = aliased(windowed, name="first_in_win")
    last_in_win = aliased(windowed, name="last_in_win")
    stmt = (
        select(
            first_in_win.c.anchor_id,
            first_in_win.c.occurred_at.label("first_seen_at"),
            first_in_win.c.value_json.label("original_value_json"),
            last_in_win.c.occurred_at.label("last_change_at"),
            last_in_win.c.kind.label("latest_kind"),
            last_in_win.c.value_json.label("current_value_json"),
        )
        .select_from(
            first_in_win.join(
                last_in_win,
                and_(
                    first_in_win.c.anchor_id == last_in_win.c.anchor_id,
                    first_in_win.c.rn_first == 1,
                    last_in_win.c.rn_last == 1,
                ),
            )
        )
        .order_by(last_in_win.c.occurred_at.desc())
    )
    rows_raw = (await db.execute(stmt)).all()

    # Compute change_counts in a second pass (cheap — one GROUP BY
    # over the indexed table per instance, bounded by the window).
    # ``COUNT(DISTINCT backup_id)`` (not ``COUNT(*)``) so a single
    # operator action that produced multiple events for the same
    # backup (e.g. a rule both edited and reordered → one
    # ``modified`` + one ``reordered`` row) counts as ONE change.
    # Without the DISTINCT the cumulative-changes heatmap would
    # over-report frequently-shuffled rules.
    counts_stmt = (
        select(
            AnchorEvent.anchor_id,
            func.count(func.distinct(AnchorEvent.backup_id)),
        )
        .where(AnchorEvent.instance_id == instance_id)
        .where(AnchorEvent.occurred_at >= since_at)
        .where(AnchorEvent.occurred_at <= until_at)
        .group_by(AnchorEvent.anchor_id)
    )
    counts_map = dict((await db.execute(counts_stmt)).all())

    import json as _json

    result_rows: list[CumulativeChangeRow] = []
    for (
        anchor_id,
        first_seen_at,
        original_value_json,
        last_change_at,
        latest_kind,
        current_value_json,
    ) in rows_raw:
        section = section_for_anchor(anchor_id)
        try:
            current_value = (
                _json.loads(current_value_json)
                if current_value_json is not None
                else None
            )
        except (TypeError, ValueError):
            current_value = None
        try:
            original_value = (
                _json.loads(original_value_json)
                if original_value_json is not None
                else None
            )
        except (TypeError, ValueError):
            original_value = None

        if section is not None and isinstance(current_value, dict):
            label = label_for_section(section, current_value)
        elif section is not None and isinstance(original_value, dict):
            label = label_for_section(section, original_value)
        else:
            # Field-shaped anchor or row with a scalar value — fall
            # back to the anchor_id tail.
            label = anchor_id.split("-", 2)[-1] if "-" in anchor_id else anchor_id

        result_rows.append(
            CumulativeChangeRow(
                anchor_id=anchor_id,
                section=section,
                label=label,
                first_seen_at=first_seen_at.isoformat(),
                last_change_at=last_change_at.isoformat(),
                change_count=int(counts_map.get(anchor_id, 0)),
                latest_kind=latest_kind,
                original_value=original_value,
                current_value=current_value,
            )
        )

    return CumulativeChangesResponse(
        since_backup_id=since_id,
        until_backup_id=until_id,
        rows=result_rows,
        indexed=True,
    )
