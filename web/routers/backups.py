"""Browse, download (single + zip), and diff backup XML files."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pfsense_shared.models import Backup, Instance

from ..dependencies import DbSession
from ..services.backup_storage import read_content, stream_raw, zip_stream

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


class ZipRequest(BaseModel):
    ids: list[int]


@router.get("", response_model=list[BackupListItem])
async def list_backups(
    db: DbSession,
    instance_id: int | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[BackupListItem]:
    stmt = (
        select(Backup, Instance.name)
        .join(Instance, Backup.instance_id == Instance.id)
        .order_by(Backup.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if instance_id is not None:
        stmt = stmt.where(Backup.instance_id == instance_id)
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
    }


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
