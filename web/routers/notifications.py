"""Notification (webhook) CRUD + test send."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from pfsense_shared.models import Job, Notification
from pfsense_shared.schemas import (
    NotificationCreate,
    NotificationRead,
    NotificationUpdate,
    SendTestNotificationCommand,
)

from ..dependencies import CurrentUser, DbSession, Ipc
from ..services import audit

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _to_read(row: Notification) -> NotificationRead:
    return NotificationRead.model_validate(
        {
            "id": row.id,
            "name": row.name,
            "url": row.url,
            "trigger": row.trigger,
            "enabled": row.enabled,
            "message_format": row.message_format,
            "include_instance_details": row.include_instance_details,
            "timeout_seconds": row.timeout_seconds,
            "headers": json.loads(row.headers_json) if row.headers_json else None,
            "payload_template": (
                json.loads(row.payload_template_json) if row.payload_template_json else None
            ),
        }
    )


@router.get("", response_model=list[NotificationRead])
async def list_notifications(db: DbSession) -> list[NotificationRead]:
    rows = db.execute(select(Notification).order_by(Notification.name)).scalars().all()
    return [_to_read(r) for r in rows]


@router.post("", response_model=NotificationRead, status_code=status.HTTP_201_CREATED)
async def create_notification(
    payload: NotificationCreate, db: DbSession, user: CurrentUser
) -> NotificationRead:
    row = Notification(
        name=payload.name,
        url=payload.url,
        trigger=payload.trigger,
        enabled=payload.enabled,
        message_format=payload.message_format,
        include_instance_details=payload.include_instance_details,
        timeout_seconds=payload.timeout_seconds,
        headers_json=json.dumps(payload.headers) if payload.headers else None,
        payload_template_json=(
            json.dumps(payload.payload_template) if payload.payload_template else None
        ),
    )
    db.add(row)
    db.flush()
    audit.record(
        db, actor_email=user["email"], action="create", resource="notification",
        resource_id=row.id, details={"name": row.name},
    )
    db.commit()
    return _to_read(row)


@router.put("/{notification_id}", response_model=NotificationRead)
async def update_notification(
    notification_id: int, payload: NotificationUpdate, db: DbSession, user: CurrentUser
) -> NotificationRead:
    row = db.get(Notification, notification_id)
    if row is None:
        raise HTTPException(404, "notification not found")

    changed: dict = {}
    for field in (
        "name", "url", "trigger", "enabled", "message_format",
        "include_instance_details", "timeout_seconds",
    ):
        val = getattr(payload, field)
        if val is not None and getattr(row, field) != val:
            setattr(row, field, val)
            changed[field] = val
    if payload.headers is not None:
        row.headers_json = json.dumps(payload.headers) if payload.headers else None
        changed["headers"] = "<updated>"
    if payload.payload_template is not None:
        row.payload_template_json = (
            json.dumps(payload.payload_template) if payload.payload_template else None
        )
        changed["payload_template"] = "<updated>"

    if changed:
        row.updated_at = datetime.now(UTC)
        audit.record(
            db, actor_email=user["email"], action="update", resource="notification",
            resource_id=row.id, details=changed,
        )
        db.commit()
    return _to_read(row)


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: int, db: DbSession, user: CurrentUser
) -> None:
    row = db.get(Notification, notification_id)
    if row is None:
        raise HTTPException(404, "notification not found")
    name = row.name
    db.delete(row)
    audit.record(
        db, actor_email=user["email"], action="delete", resource="notification",
        resource_id=notification_id, details={"name": name},
    )
    db.commit()


@router.post("/{notification_id}/test")
async def send_test(
    notification_id: int, db: DbSession, user: CurrentUser, ipc: Ipc
) -> dict[str, int]:
    if db.get(Notification, notification_id) is None:
        raise HTTPException(404, "notification not found")
    job = Job(kind="test_notification", requested_by=user["email"])
    db.add(job)
    db.flush()
    audit.record(
        db, actor_email=user["email"], action="trigger", resource="notification_test",
        resource_id=notification_id,
    )
    db.commit()
    await ipc.send(
        SendTestNotificationCommand(notification_id=notification_id, job_id=job.id)
    )
    return {"job_id": job.id}
