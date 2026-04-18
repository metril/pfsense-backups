"""Global backup/file-layout settings + logging settings (singleton rows)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from pfsense_shared.models import BackupSettings, LoggingSettings
from pfsense_shared.schemas import (
    BackupSettingsRead,
    BackupSettingsUpdate,
    LoggingSettingsRead,
    LoggingSettingsUpdate,
)

from ..dependencies import CurrentUser, DbSession
from ..services import audit

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_all(db: DbSession) -> dict[str, Any]:
    bs = await db.get(BackupSettings, 1)
    ls = await db.get(LoggingSettings, 1)
    return {
        "backup": BackupSettingsRead.model_validate(bs).model_dump() if bs else None,
        "logging": LoggingSettingsRead.model_validate(ls).model_dump() if ls else None,
    }


@router.put("/backup", response_model=BackupSettingsRead)
async def put_backup(
    payload: BackupSettingsUpdate, db: DbSession, user: CurrentUser
) -> BackupSettingsRead:
    row = await db.get(BackupSettings, 1)
    if row is None:
        row = BackupSettings(id=1)
        db.add(row)
    changed: dict[str, Any] = {}
    for field in ("filename_format", "timestamp_format", "directory"):
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
    return BackupSettingsRead.model_validate(row)


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
