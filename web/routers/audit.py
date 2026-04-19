"""Audit log viewer — surfaces the existing ``audit_log`` rows to the UI.

Every mutating action (instance create/update/delete, backup import,
backup tag/note edits, backup delete, test triggers) already records an
entry here. This endpoint just makes them browsable.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from pfsense_shared.models import AuditLog

from ..dependencies import CurrentUser, DbSession

router = APIRouter(prefix="/api/audit", tags=["audit"])


class AuditEntry(BaseModel):
    id: int
    ts: str
    actor_email: str
    action: str
    resource: str
    resource_id: str | None
    details: dict[str, Any] | None


@router.get("", response_model=list[AuditEntry])
async def list_audit(
    db: DbSession,
    user: CurrentUser,
    actor: str | None = None,
    action: str | None = None,
    resource: str | None = None,
    ts_from: datetime | None = None,
    ts_to: datetime | None = None,
    limit: int = Query(default=200, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[AuditEntry]:
    _ = user  # auth guard only
    stmt = select(AuditLog).order_by(AuditLog.ts.desc()).limit(limit).offset(offset)
    if actor:
        stmt = stmt.where(AuditLog.actor_email == actor)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if resource:
        stmt = stmt.where(AuditLog.resource == resource)
    if ts_from is not None:
        stmt = stmt.where(AuditLog.ts >= ts_from)
    if ts_to is not None:
        stmt = stmt.where(AuditLog.ts <= ts_to)
    rows = (await db.scalars(stmt)).all()
    return [
        AuditEntry(
            id=r.id,
            ts=r.ts.isoformat(),
            actor_email=r.actor_email,
            action=r.action,
            resource=r.resource,
            resource_id=r.resource_id,
            details=json.loads(r.details_json) if r.details_json else None,
        )
        for r in rows
    ]


@router.get("/facets")
async def audit_facets(db: DbSession, user: CurrentUser) -> dict[str, list[str]]:
    """Distinct values for actor, action, and resource — fuel for dropdowns."""
    _ = user
    actors = (await db.scalars(select(AuditLog.actor_email).distinct())).all()
    actions = (await db.scalars(select(AuditLog.action).distinct())).all()
    resources = (await db.scalars(select(AuditLog.resource).distinct())).all()
    return {
        "actors": sorted(a for a in actors if a),
        "actions": sorted(a for a in actions if a),
        "resources": sorted(r for r in resources if r),
    }
