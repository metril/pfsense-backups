"""Audit-log helper. Call from mutating routes after a successful write."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from pfsense_shared.models import AuditLog


def record(
    session: Session,
    *,
    actor_email: str,
    action: str,
    resource: str,
    resource_id: str | int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    entry = AuditLog(
        actor_email=actor_email,
        action=action,
        resource=resource,
        resource_id=str(resource_id) if resource_id is not None else None,
        details_json=json.dumps(details, default=str) if details else None,
    )
    session.add(entry)
