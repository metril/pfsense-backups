"""Per-instance cron schedule view + edit."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from pfsense_shared.models import Instance
from pfsense_shared.schemas import ReloadScheduleCommand, ScheduleUpdate

from ..dependencies import CurrentUser, DbSession, Ipc
from ..services import audit
from ..services.cron_utils import describe, next_runs, validate, validate_tz

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


def _schedule_row(inst: Instance) -> dict[str, Any]:
    description = describe(inst.cron_expression) if inst.cron_expression else ""
    try:
        nxt = (
            [r.isoformat() for r in next_runs(inst.cron_expression, inst.cron_timezone, 3)]
            if inst.cron_expression
            else []
        )
    except Exception:
        nxt = []
    return {
        "instance_id": inst.id,
        "instance_name": inst.name,
        "cron_expression": inst.cron_expression,
        "cron_timezone": inst.cron_timezone,
        "enabled": inst.enabled,
        "description": description,
        "next_runs": nxt,
    }


@router.get("")
async def list_schedules(db: DbSession) -> list[dict[str, Any]]:
    rows = (await db.scalars(select(Instance).order_by(Instance.name))).all()
    return [_schedule_row(r) for r in rows]


@router.get("/{instance_id}")
async def get_schedule(instance_id: int, db: DbSession) -> dict[str, Any]:
    inst = await db.get(Instance, instance_id)
    if inst is None:
        raise HTTPException(404, "instance not found")
    return _schedule_row(inst)


@router.put("/{instance_id}")
async def put_schedule(
    instance_id: int,
    payload: ScheduleUpdate,
    db: DbSession,
    user: CurrentUser,
    ipc: Ipc,
) -> dict[str, Any]:
    inst = await db.get(Instance, instance_id)
    if inst is None:
        raise HTTPException(404, "instance not found")

    if payload.cron_expression:
        try:
            validate(payload.cron_expression)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
    try:
        validate_tz(payload.cron_timezone)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None

    inst.cron_expression = payload.cron_expression
    inst.cron_timezone = payload.cron_timezone
    inst.enabled = payload.enabled

    audit.record(
        db,
        actor_email=user["email"],
        action="update",
        resource="schedule",
        resource_id=instance_id,
        details={
            "cron_expression": payload.cron_expression,
            "cron_timezone": payload.cron_timezone,
            "enabled": payload.enabled,
        },
    )
    await db.commit()
    await ipc.send(ReloadScheduleCommand(instance_id=instance_id))
    return _schedule_row(inst)


@router.get("/_tools/preview")
async def preview(cron: str, tz: str = "UTC") -> dict[str, Any]:
    """Validate + describe a cron expression without persisting anything.

    Used by the frontend CronEditor for the live human-readable preview.
    """
    try:
        validate(cron)
        validate_tz(tz)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return {
        "cron": cron,
        "description": describe(cron),
        "next_runs": [r.isoformat() for r in next_runs(cron, tz, 3)],
    }
