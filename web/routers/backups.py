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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pfsense_shared.models import Backup, Instance, Job
from pfsense_shared.paths import BACKUPS_DIR  # noqa: F401 — used by /anchor-history
from pfsense_shared.pfsense_anchor_values import resolve_anchor_value
from pfsense_shared.pfsense_crypto import (
    PfSenseCryptoError,
    decrypt_pfsense_backup,
    looks_encrypted,
)
from pfsense_shared.pfsense_diff import ConfigDiff, diff_configs
from pfsense_shared.pfsense_parser import ParsedConfig
from pfsense_shared.pfsense_parser import parse as parse_pfsense_xml
from pfsense_shared.pfsense_positions import build_positions
from pfsense_shared.schemas import (
    BackupUpdate,
    ReencryptAllBackupsCommand,
    RunBackupAllCommand,
)

from ..dependencies import CryptoDep, CurrentUser, DbSession, Ipc
from ..services import audit
from ..services.backup_storage import read_content, stream_raw, zip_stream

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backups", tags=["backups"])


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
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[BackupListItem]:
    col = _SORTABLE.get(sort, Backup.started_at)
    direction = col.desc() if order.lower() == "desc" else col.asc()
    stmt = (
        select(Backup, Instance.name)
        .join(Instance, Backup.instance_id == Instance.id)
        .order_by(direction)
        .limit(limit)
        .offset(offset)
    )
    if instance_id is not None:
        stmt = stmt.where(Backup.instance_id == instance_id)
    if started_from is not None:
        stmt = stmt.where(Backup.started_at >= started_from)
    if started_to is not None:
        stmt = stmt.where(Backup.started_at <= started_to)
    rows = (await db.execute(stmt)).all()
    return [
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
        )
        for b, name in rows
    ]


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
        raise HTTPException(
            404,
            f"backup file missing on disk: {path}",
        )
    return b, path


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
        "path": b.path,
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
    backup_id: int, db: DbSession, user: CurrentUser
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
    await db.delete(b)
    audit.record(
        db, actor_email=user["email"], action="delete", resource="backup",
        resource_id=backup_id,
        details={
            "filename": filename,
            "instance_id": instance_id,
            "file_removed": file_removed,
            "file_missing": file_missing,
        },
    )
    await db.commit()
    log.info(
        "Deleted backup id=%d filename=%s (file_removed=%s file_missing=%s)",
        backup_id, filename, file_removed, file_missing,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _row_encrypt_password(row: Backup, crypto) -> str:
    """Fernet-decrypt the per-backup encryption password, or raise 409.

    Prefers the per-row ciphertext so a rotated instance-level password
    still lets us open historical backups. Refusing rather than falling
    back to the instance password keeps the contract explicit.
    """
    if not row.encrypt_password_ct:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "cannot decrypt backup: no per-row password stored. "
            "Download the raw encrypted file and decrypt offline.",
        )
    try:
        return crypto.decrypt(row.encrypt_password_ct)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"cannot decrypt backup password: {exc}",
        ) from exc


def _decrypt_row_content(row: Backup, path: Path, crypto) -> bytes:
    """Read the on-disk blob and return plaintext XML bytes.

    Handles gzipped rows transparently, picks the KDF based on wrapper
    headers (with fallback), and translates known failure modes into
    HTTPException so the frontend can show a sensible error toast.
    """
    import gzip

    if path.suffix == ".gz" or row.compressed:
        with gzip.open(path, "rb") as gz:
            raw = gz.read()
    else:
        raw = path.read_bytes()
    if not looks_encrypted(raw):
        # Marked encrypted in the DB but the file looks like plain XML —
        # happens with historical rows imported before this feature. Fall
        # through to returning the raw content.
        return raw
    password = _row_encrypt_password(row, crypto)
    try:
        return decrypt_pfsense_backup(raw, password)
    except PfSenseCryptoError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"cannot decrypt backup — password missing or KDF mismatch ({exc})",
        ) from exc


@router.get("/{backup_id}/content")
async def get_content(
    backup_id: int, db: DbSession, user: CurrentUser, crypto: CryptoDep
) -> Response:
    """Decompressed XML text (used by the diff view).

    When the row is encrypted, we Fernet-decrypt the stored per-backup
    password, then decrypt the on-disk blob into plaintext XML — all
    in memory. The decrypted XML never lands on disk. The decrypt event
    is audited so operators can see who read plaintext pfSense config
    (which includes cert keys, VPN PSKs, admin password hashes).
    """
    row, path = await _load(db, backup_id)
    if row.encrypted:
        content = await asyncio.to_thread(_decrypt_row_content, row, path, crypto)
        audit.record(
            db, actor_email=user["email"], action="view_decrypted",
            resource="backup", resource_id=backup_id,
            details={"filename": row.filename},
        )
        await db.commit()
    else:
        content = await asyncio.to_thread(read_content, path)
    return Response(content=content, media_type="application/xml")


@router.get("/{backup_id}/download", response_model=None)
async def download(
    backup_id: int,
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
    """
    row, path = await _load(db, backup_id)

    if row.encrypted and not raw:
        plaintext = await asyncio.to_thread(_decrypt_row_content, row, path, crypto)
        download_name = path.name
        # Strip .gz / .enc-ish suffixes so the user gets a `.xml` they
        # can open directly.
        for suffix in (".gz",):
            if download_name.endswith(suffix):
                download_name = download_name[: -len(suffix)]
        audit.record(
            db, actor_email=user["email"], action="download_decrypted",
            resource="backup", resource_id=backup_id,
            details={"filename": row.filename},
        )
        await db.commit()
        return Response(
            content=plaintext,
            media_type="application/xml",
            headers={
                "Content-Disposition": f'attachment; filename="{download_name}"'
            },
        )

    audit.record(
        db, actor_email=user["email"],
        action="download_raw" if row.encrypted else "download",
        resource="backup", resource_id=backup_id,
        details={"filename": row.filename},
    )
    await db.commit()

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
    backup_id: int, db: DbSession, user: CurrentUser, crypto: CryptoDep
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
    """
    row, path = await _load(db, backup_id)
    if row.encrypted:
        content = await asyncio.to_thread(_decrypt_row_content, row, path, crypto)
        audit.record(
            db, actor_email=user["email"], action="view_decrypted",
            resource="backup", resource_id=backup_id,
            details={"filename": row.filename, "via": "parsed"},
        )
        await db.commit()
    else:
        content = await asyncio.to_thread(read_content, path)
    if isinstance(content, str):
        content_bytes = content.encode("utf-8")
    else:
        content_bytes = content
    parsed = await asyncio.to_thread(parse_pfsense_xml, content_bytes)
    # Pass ``parsed`` so firewall + NAT rule anchors pair 1:1 with the
    # parser's synthesized ``r.key`` (tracker-less rules get a hash
    # fallback that the frontend also emits via ``rowAnchorId``).
    positions = await asyncio.to_thread(build_positions, content_bytes, parsed)
    return ParsedBackupResponse(config=parsed, positions=positions)


@router.get("/diff/pair/parsed", response_model=ConfigDiff)
async def diff_pair_parsed(
    a: int, b: int, db: DbSession, user: CurrentUser, crypto: CryptoDep
) -> ConfigDiff:
    """Semantic diff between two parsed configs.

    Decrypts both sides in memory, parses each, then runs the
    structured diff engine. Single audit entry per pair when either
    side is encrypted.
    """
    a_row, a_path = await _load(db, a)
    b_row, b_path = await _load(db, b)

    def _get(row: Backup, path: Path) -> bytes | str:
        if row.encrypted:
            return _decrypt_row_content(row, path, crypto)
        return read_content(path)

    a_bytes = await asyncio.to_thread(_get, a_row, a_path)
    b_bytes = await asyncio.to_thread(_get, b_row, b_path)
    if a_row.encrypted or b_row.encrypted:
        audit.record(
            db, actor_email=user["email"], action="view_decrypted",
            resource="backup_diff", resource_id=None,
            details={"a": a_row.id, "b": b_row.id, "via": "parsed"},
        )
        await db.commit()
    a_parsed = await asyncio.to_thread(parse_pfsense_xml, a_bytes)
    b_parsed = await asyncio.to_thread(parse_pfsense_xml, b_bytes)
    return await asyncio.to_thread(diff_configs, a_parsed, b_parsed)


@router.get("/diff/pair")
async def diff_pair(
    a: int, b: int, db: DbSession, user: CurrentUser, crypto: CryptoDep
) -> dict[str, Any]:
    """Return both backups' decompressed XML content for a side-by-side diff view.

    Encrypted rows get decrypted in memory using their per-backup
    password so the diff view sees plaintext XML on either side. The
    decrypt event is audited so operators can see who read plaintext
    pfSense config via the diff path.
    """
    a_row, a_path = await _load(db, a)
    b_row, b_path = await _load(db, b)

    def _get(row: Backup, path: Path) -> bytes:
        if row.encrypted:
            return _decrypt_row_content(row, path, crypto)
        return read_content(path)

    def _as_str(v: bytes | str) -> str:
        return v.decode("utf-8", errors="replace") if isinstance(v, bytes) else v

    a_content = _as_str(await asyncio.to_thread(_get, a_row, a_path))
    b_content = _as_str(await asyncio.to_thread(_get, b_row, b_path))
    if a_row.encrypted or b_row.encrypted:
        audit.record(
            db, actor_email=user["email"], action="view_decrypted",
            resource="backup_diff", resource_id=None,
            details={"a": a_row.id, "b": b_row.id},
        )
        await db.commit()
    return {
        "a": {
            "id": a_row.id,
            "filename": a_row.filename,
            "started_at": a_row.started_at.isoformat(),
            "content": a_content,
        },
        "b": {
            "id": b_row.id,
            "filename": b_row.filename,
            "started_at": b_row.started_at.isoformat(),
            "content": b_content,
        },
    }


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
    """Version of ``_decrypt_row_content`` that operates on the plain
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
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "cannot decrypt backup: no per-row password stored. "
            "Download the raw encrypted file and decrypt offline.",
        )
    try:
        password = crypto.decrypt(row.encrypt_password_ct)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"cannot decrypt backup password: {exc}",
        ) from exc
    try:
        return decrypt_pfsense_backup(raw, password)
    except PfSenseCryptoError as exc:
        raise HTTPException(
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

    Walks every successful backup for the instance in chronological
    order, decrypts + parses each, resolves ``anchor`` to the value
    it points at in that backup, and records transitions. Used by
    the v0.24.0 blame drawer in the history page.

    Cost: decrypts + parses every backup on each request. Backups
    for a single instance are typically dozens to a few hundred;
    parsing is a few-hundred-ms per config. Result is deterministic
    and idempotent; frontend caches aggressively via TanStack Query.

    Connection discipline: the dependency-injected ``db`` session
    holds a pool connection for the lifetime of this handler. For
    instances with many backups the walk can take tens of seconds,
    so we fetch the rows, snapshot them into plain objects, then
    ``await db.close()`` to free the connection BEFORE entering the
    parse thread. A fresh session is opened from the factory for
    the trailing audit write. Under modest concurrency this is the
    difference between pool-exhaustion under load and smooth-running.

    Audited as ``view_decrypted`` once per request (not once per
    encrypted backup) — operators reviewing blame data see only one
    audit entry per drill-in.
    """
    # Load instance + its successful backups in ascending order.
    inst_row = (
        await db.execute(select(Instance).where(Instance.id == instance_id))
    ).scalar_one_or_none()
    if inst_row is None:
        raise HTTPException(status_code=404, detail="instance not found")

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
                raw_bytes = _read_for_walk(s, crypto)
            else:
                raw_bytes = read_content(_row_path(s.path))
            parsed = parse_pfsense_xml(raw_bytes)
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

    entries = await asyncio.to_thread(_gather)

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
    )


# Sentinel so the "first iteration is always a change" pattern works
# even when the value happens to be ``None``.
_MISSING = object()
