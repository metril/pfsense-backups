"""Global backup/file-layout settings + logging settings (singleton rows)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from pfsense_shared.models import BackupSettings, LoggingSettings
from pfsense_shared.schemas import (
    BackupSettingsRead,
    BackupSettingsUpdate,
    LoggingSettingsRead,
    LoggingSettingsUpdate,
    ReloadScheduleCommand,
)

from ..dependencies import CurrentUser, DbSession, Ipc
from ..services import audit
from ..services.cron_utils import validate_tz

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
