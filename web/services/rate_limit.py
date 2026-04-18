"""slowapi-backed rate limiter (A3).

Design:
  - One module-level ``Limiter`` instance. Routes use ``@limiter.limit(...)``
    decorators directly; slowapi's ``SlowAPIMiddleware`` is NOT registered —
    it added an opinionated default-limits path that fought our factory
    pattern. We apply limits exclusively per-route.
  - Per-route limit strings are resolved at call time from env vars
    (``RATE_LIMIT_LOGIN``, ``RATE_LIMIT_WS``). ``configure_from_settings()``
    copies a ``WebSettings`` into those env vars so a programmatic config
    path works too.
  - Kill-switch: ``RATE_LIMIT_ENABLED=false`` (or settings.rate_limit_enabled=False)
    flips ``limiter.enabled`` so every decorator becomes a no-op.

Keying prefers the first entry of ``X-Forwarded-For`` so Traefik-forwarded IPs
are respected; anything bypassing Traefik is on the trusted docker network.
"""

from __future__ import annotations

import logging
import os

from fastapi import Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

log = logging.getLogger(__name__)


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if xff:
        return xff
    return get_remote_address(request)


def _env_enabled() -> bool:
    return os.environ.get("RATE_LIMIT_ENABLED", "true").lower() not in ("0", "false", "no")


limiter = Limiter(key_func=_client_ip, enabled=_env_enabled())


def configure_from_settings(settings) -> None:  # type: ignore[no-untyped-def]
    """Copy rate-limit settings into env vars + flip limiter.enabled."""
    limiter.enabled = settings.rate_limit_enabled
    os.environ["RATE_LIMIT_ENABLED"] = "true" if settings.rate_limit_enabled else "false"
    os.environ["RATE_LIMIT_DEFAULT"] = settings.rate_limit_default
    os.environ["RATE_LIMIT_LOGIN"] = settings.rate_limit_login
    os.environ["RATE_LIMIT_WS"] = settings.rate_limit_ws


def login_limit() -> str:
    return os.environ.get("RATE_LIMIT_LOGIN", "10/minute")


def ws_limit() -> str:
    return os.environ.get("RATE_LIMIT_WS", "30/minute")


async def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded  # noqa: ARG001
) -> JSONResponse:
    detail = f"rate limit exceeded: {exc.detail}"
    log.warning(
        "%s %s from %s: %s",
        request.method,
        request.url.path,
        _client_ip(request),
        detail,
    )
    response = JSONResponse(status_code=429, content={"detail": detail})
    response.headers["Retry-After"] = "60"
    return response
