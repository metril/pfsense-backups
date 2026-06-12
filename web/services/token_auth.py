"""Bearer-token authentication for automation clients (F7).

The middleware calls ``authenticate_bearer`` before the session check.
Positive lookups are cached for ``_CACHE_TTL_SECONDS`` so steady-state
API traffic costs zero DB hits; the trade-off is that revoking /
disabling a token can take up to the TTL to bite. ``last_used_at``
writes are throttled to once per ``_LAST_USED_WRITE_SECONDS`` per
token so the column stays informative without a write per request.
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import UTC, datetime
from typing import Any

from cachetools import TTLCache
from sqlalchemy import select
from starlette.requests import Request

from pfsense_shared.models import ApiToken

log = logging.getLogger(__name__)

TOKEN_PREFIX = "pfsb_"

_CACHE_TTL_SECONDS = 60
_LAST_USED_WRITE_SECONDS = 300

# hash → resolved identity dict. Negative results are NOT cached so a
# just-created token works immediately.
_cache: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=256, ttl=_CACHE_TTL_SECONDS)
_last_used_write_at: dict[str, float] = {}


def hash_token(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def clear_cache() -> None:
    """Drop cached identities — called by the tokens router on revoke /
    disable so changes apply immediately instead of after the TTL."""
    _cache.clear()


async def authenticate_bearer(request: Request) -> dict[str, Any] | None:
    """Resolve an ``Authorization: Bearer pfsb_…`` header to an identity
    dict, or None when the request carries no (valid) token."""
    auth = request.headers.get("authorization")
    if not auth or not auth.startswith("Bearer "):
        return None
    secret = auth[7:].strip()
    if not secret.startswith(TOKEN_PREFIX):
        return None
    h = hash_token(secret)

    user = _cache.get(h)
    if user is None:
        now = datetime.now(UTC)
        async with request.app.state.session_factory() as s:
            row = (
                await s.execute(
                    select(ApiToken).where(
                        ApiToken.token_hash == h,
                        ApiToken.enabled.is_(True),
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            expires = row.expires_at
            if expires is not None and expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if expires is not None and expires <= now:
                return None
            user = {
                "email": f"token:{row.name}",
                "name": row.name,
                "token_id": row.id,
                "token_scope": row.scope,
            }
            _cache[h] = user

    await _touch_last_used(request, h, user["token_id"])
    return user


async def _touch_last_used(request: Request, h: str, token_id: int) -> None:
    mono = time.monotonic()
    last = _last_used_write_at.get(h)
    if last is not None and mono - last < _LAST_USED_WRITE_SECONDS:
        return
    _last_used_write_at[h] = mono
    try:
        async with request.app.state.session_factory() as s:
            row = await s.get(ApiToken, token_id)
            if row is not None:
                row.last_used_at = datetime.now(UTC)
                await s.commit()
    except Exception as exc:
        log.debug("last_used_at touch failed for token %d: %s", token_id, exc)
