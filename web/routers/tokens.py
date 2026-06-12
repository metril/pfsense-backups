"""API token management (F7). Session-auth ONLY — a bearer token can
never list, mint, alter, or revoke tokens (privilege containment: a
leaked automation token must not be able to mint itself successors).
The plaintext secret appears exactly once, in the create response.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from pfsense_shared.models import ApiToken
from pfsense_shared.schemas import (
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenRead,
    ApiTokenUpdate,
)

from ..dependencies import CurrentUser, DbSession
from ..services import audit
from ..services.token_auth import TOKEN_PREFIX, clear_cache, hash_token

router = APIRouter(prefix="/api/tokens", tags=["tokens"])


def _session_only(request: Request) -> None:
    if getattr(request.state, "api_user", None) is not None:
        raise HTTPException(403, "token management requires a browser session")


@router.get("", response_model=list[ApiTokenRead])
async def list_tokens(
    request: Request, db: DbSession, user: CurrentUser
) -> list[ApiTokenRead]:
    _session_only(request)
    rows = (
        await db.scalars(select(ApiToken).order_by(ApiToken.created_at.desc()))
    ).all()
    return [ApiTokenRead.model_validate(r) for r in rows]


@router.post("", response_model=ApiTokenCreated, status_code=status.HTTP_201_CREATED)
async def create_token(
    request: Request, payload: ApiTokenCreate, db: DbSession, user: CurrentUser
) -> ApiTokenCreated:
    _session_only(request)
    existing = (
        await db.scalars(select(ApiToken).where(ApiToken.name == payload.name))
    ).first()
    if existing is not None:
        raise HTTPException(409, f"token name {payload.name!r} already exists")

    secret = TOKEN_PREFIX + secrets.token_urlsafe(32)
    row = ApiToken(
        name=payload.name,
        token_hash=hash_token(secret),
        prefix=secret[:12],
        scope=payload.scope,
        enabled=True,
        created_by=user["email"],
        expires_at=(
            datetime.now(UTC) + timedelta(days=payload.expires_in_days)
            if payload.expires_in_days is not None
            else None
        ),
    )
    db.add(row)
    await db.flush()
    audit.record(
        db, actor_email=user["email"], action="create", resource="api_token",
        resource_id=row.id, details={"name": row.name, "scope": row.scope},
    )
    await db.commit()
    return ApiTokenCreated(
        id=row.id,
        name=row.name,
        prefix=row.prefix,
        scope=row.scope,  # type: ignore[arg-type]
        enabled=row.enabled,
        created_by=row.created_by,
        created_at=row.created_at,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        token=secret,
    )


@router.patch("/{token_id}", response_model=ApiTokenRead)
async def update_token(
    request: Request,
    token_id: int,
    payload: ApiTokenUpdate,
    db: DbSession,
    user: CurrentUser,
) -> ApiTokenRead:
    _session_only(request)
    row = await db.get(ApiToken, token_id)
    if row is None:
        raise HTTPException(404, "token not found")
    if payload.enabled is not None and payload.enabled != row.enabled:
        row.enabled = payload.enabled
        audit.record(
            db, actor_email=user["email"],
            action="update", resource="api_token", resource_id=row.id,
            details={"name": row.name, "enabled": row.enabled},
        )
        await db.commit()
        # Disabling must bite immediately, not after the auth-cache TTL.
        clear_cache()
    return ApiTokenRead.model_validate(row)


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_token(
    request: Request, token_id: int, db: DbSession, user: CurrentUser
) -> None:
    _session_only(request)
    row = await db.get(ApiToken, token_id)
    if row is None:
        raise HTTPException(404, "token not found")
    name = row.name
    await db.delete(row)
    audit.record(
        db, actor_email=user["email"], action="delete", resource="api_token",
        resource_id=token_id, details={"name": name},
    )
    await db.commit()
    clear_cache()
