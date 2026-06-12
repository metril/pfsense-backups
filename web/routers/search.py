"""Global config search (F4): substring search across every instance's
anchor-event history — "when did 192.0.2.5 appear anywhere?".

Matches ``AnchorEvent.value_json`` (the JSON-encoded post-change value)
and ``anchor_id``. A leading-wildcard LIKE is a full scan on SQLite
either way, so there's no index to add here; the result set is capped
and keyset-paginated (``before_id``) so deep pages don't re-serialize
ever-larger offsets. On a future Postgres backend this is the place
for a ``pg_trgm`` GIN index over ``value_json``.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from pfsense_shared.anchor_events import section_for_anchor
from pfsense_shared.models import AnchorEvent, Instance
from pfsense_shared.pfsense_labels import label_for_section

from ..dependencies import CurrentUser, DbSession
from ..services import audit

router = APIRouter(prefix="/api/search", tags=["search"])

_EXCERPT_RADIUS = 40
_MAX_LIMIT = 100


class SearchHit(BaseModel):
    event_id: int
    instance_id: int
    instance_name: str
    backup_id: int
    occurred_at: str
    anchor_id: str
    kind: str
    section: str | None
    label: str
    excerpt: str


class SearchResponse(BaseModel):
    hits: list[SearchHit]
    has_more: bool


def _escape_like(q: str) -> str:
    return (
        q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )


def _excerpt(value_json: str | None, q: str) -> str:
    if not value_json:
        return ""
    idx = value_json.lower().find(q.lower())
    if idx < 0:
        return value_json[: _EXCERPT_RADIUS * 2]
    start = max(0, idx - _EXCERPT_RADIUS)
    end = min(len(value_json), idx + len(q) + _EXCERPT_RADIUS)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(value_json) else ""
    return f"{prefix}{value_json[start:end]}{suffix}"


def _label(anchor_id: str, section: str | None, value_json: str | None) -> str:
    if section and value_json:
        try:
            decoded = json.loads(value_json)
        except (TypeError, ValueError):
            decoded = None
        if isinstance(decoded, dict):
            label = label_for_section(section, decoded)
            if label and label != "?":
                return label
    # Fall back to the anchor tail — still uniquely identifying.
    return anchor_id.split("-", 2)[-1]


@router.get("", response_model=SearchResponse)
async def search(
    db: DbSession,
    user: CurrentUser,
    q: str = Query(min_length=2, max_length=256),
    instance_id: int | None = Query(default=None),
    kind: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=_MAX_LIMIT),
    before_id: int | None = Query(default=None),
) -> SearchResponse:
    pattern = f"%{_escape_like(q)}%"
    stmt = (
        select(AnchorEvent, Instance.name)
        .join(Instance, Instance.id == AnchorEvent.instance_id)
        .where(
            AnchorEvent.value_json.like(pattern, escape="\\")
            | AnchorEvent.anchor_id.like(pattern, escape="\\")
        )
        .order_by(AnchorEvent.occurred_at.desc(), AnchorEvent.id.desc())
        .limit(limit + 1)
    )
    if instance_id is not None:
        stmt = stmt.where(AnchorEvent.instance_id == instance_id)
    if kind is not None:
        if kind not in ("added", "modified", "removed", "reordered"):
            raise HTTPException(422, "kind must be added|modified|removed|reordered")
        stmt = stmt.where(AnchorEvent.kind == kind)
    if before_id is not None:
        stmt = stmt.where(AnchorEvent.id < before_id)

    rows = (await db.execute(stmt)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    hits: list[SearchHit] = []
    for ev, instance_name in rows:
        section = section_for_anchor(ev.anchor_id)
        hits.append(
            SearchHit(
                event_id=ev.id,
                instance_id=ev.instance_id,
                instance_name=instance_name,
                backup_id=ev.backup_id,
                occurred_at=ev.occurred_at.isoformat(),
                anchor_id=ev.anchor_id,
                kind=ev.kind,
                section=section,
                label=_label(ev.anchor_id, section, ev.value_json),
                excerpt=_excerpt(ev.value_json, q),
            )
        )

    audit.record(
        db, actor_email=user["email"], action="view", resource="search",
        details={"q": q, "hits": len(hits)},
    )
    await db.commit()
    return SearchResponse(hits=hits, has_more=has_more)
