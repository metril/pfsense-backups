"""Browse, download (single + zip), and diff backup XML files."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pfsense_shared.models import Backup, Instance
from pfsense_shared.schemas import BackupUpdate

from ..dependencies import CurrentUser, DbSession
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


class ZipRequest(BaseModel):
    ids: list[int]


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
        )
        for b, name in rows
    ]


async def _load(db: AsyncSession, backup_id: int) -> tuple[Backup, Path]:
    b = await db.get(Backup, backup_id)
    if b is None:
        raise HTTPException(404, "backup not found")
    path = Path(b.path)
    if not path.is_file():
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


@router.get("/{backup_id}/content")
async def get_content(backup_id: int, db: DbSession) -> Response:
    """Decompressed XML text (used by the diff view)."""
    _, path = await _load(db, backup_id)
    # File read is blocking on a small-ish file; offload to thread.
    content = await asyncio.to_thread(read_content, path)
    return Response(content=content, media_type="application/xml")


@router.get("/{backup_id}/download")
async def download(backup_id: int, db: DbSession) -> StreamingResponse:
    """Raw bytes (gzipped if stored that way)."""
    _, path = await _load(db, backup_id)

    async def body() -> AsyncIterator[bytes]:
        for chunk in await asyncio.to_thread(lambda: list(stream_raw(path))):
            yield chunk

    return StreamingResponse(
        body(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
    )


@router.post("/download-zip")
async def download_zip(body: ZipRequest, db: DbSession) -> StreamingResponse:
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


@router.get("/diff/pair")
async def diff_pair(a: int, b: int, db: DbSession) -> dict[str, Any]:
    """Return both backups' decompressed XML content for a side-by-side diff view."""
    a_row, a_path = await _load(db, a)
    b_row, b_path = await _load(db, b)
    a_content = await asyncio.to_thread(read_content, a_path)
    b_content = await asyncio.to_thread(read_content, b_path)
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
