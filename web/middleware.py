"""AuthRequiredMiddleware: enforces a session cookie on protected routes.

Allowlist matches anything the browser needs to bootstrap + the auth endpoints.
API requests without a session return 401 JSON; HTML requests get a 302 to /login.
Also emits CSRF-protection checks for mutating HTTP methods.
"""

from __future__ import annotations

import hmac
import logging
import re
import secrets
from collections.abc import Awaitable, Callable

from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .services.token_auth import authenticate_bearer

log = logging.getLogger(__name__)

# Routes that do NOT require a session cookie.
_PUBLIC_PATTERNS = [
    re.compile(r"^/api/auth/"),
    re.compile(r"^/api/health$"),
    re.compile(r"^/assets/"),
    re.compile(r"^/favicon"),
    re.compile(r"^/$"),
]

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
_CSRF_EXEMPT_PATHS = (
    "/api/auth/",           # Auth flow uses the OIDC state param, not our CSRF token.
)

CSRF_COOKIE = "csrftoken"
CSRF_HEADER = "X-CSRF-Token"


def csrf_cookie_secure(request: Request) -> bool:
    """Cookie ``secure`` flag respects ``settings.dev_mode`` (H13) so
    local-dev over http://localhost doesn't drop the cookie."""
    return not getattr(request.app.state.settings, "dev_mode", False)


def set_csrf_cookie(response: Response, value: str, secure: bool) -> None:
    """Single place that knows the CSRF cookie's attributes — used by the
    middleware and the ``/api/auth/csrf`` endpoint so the two can't drift."""
    response.set_cookie(
        key=CSRF_COOKIE,
        value=value,
        httponly=False,   # SPA must read it to echo via X-CSRF-Token
        secure=secure,
        samesite="lax",
        path="/",
    )


def _is_public(path: str) -> bool:
    return any(p.search(path) for p in _PUBLIC_PATTERNS)


def _wants_json(request: Request) -> bool:
    if request.url.path.startswith("/api/"):
        return True
    return "application/json" in request.headers.get("accept", "")


class AuthRequiredMiddleware(BaseHTTPMiddleware):
    """H1: the CSRF cookie is set on EVERY response (not only when missing)
    so the first mutating request from a brand-new client sees a valid
    double-submit pair in its own response cycle rather than racing against
    a later GET.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        csrf_value = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)
        cookie_secure = csrf_cookie_secure(request)

        path = request.url.path
        if not _is_public(path):
            # F7: bearer tokens authenticate before the session check.
            # Token requests skip CSRF — a bearer header is never
            # attached ambiently by a browser, which is the only attack
            # CSRF defends against. Scope is enforced here by method:
            # ``read`` tokens get GET/HEAD only.
            api_user = await authenticate_bearer(request)
            if api_user is not None:
                if api_user.get("token_scope") != "write" and (
                    request.method not in ("GET", "HEAD")
                ):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "token scope is read-only"},
                    )
                request.state.api_user = api_user
                return await call_next(request)

            user = request.session.get("user")
            if not user:
                if _wants_json(request):
                    response: Response = JSONResponse(
                        status_code=401, content={"detail": "not authenticated"}
                    )
                else:
                    response = RedirectResponse(
                        url="/api/auth/login", status_code=302
                    )
                self._set_csrf_cookie(response, csrf_value, cookie_secure)
                return response

            # CSRF: double-submit check on mutating requests (outside /api/auth/).
            exempt = any(path.startswith(p) for p in _CSRF_EXEMPT_PATHS)
            if request.method in _MUTATING and not exempt:
                sent = request.headers.get(CSRF_HEADER)
                if not sent or not hmac.compare_digest(sent, csrf_value):
                    log.warning("CSRF check failed for %s %s", request.method, path)
                    response = JSONResponse(
                        status_code=403, content={"detail": "CSRF token missing or invalid"}
                    )
                    self._set_csrf_cookie(response, csrf_value, cookie_secure)
                    return response

        response = await call_next(request)
        self._set_csrf_cookie(response, csrf_value, cookie_secure)
        return response

    @staticmethod
    def _set_csrf_cookie(response: Response, value: str, secure: bool) -> None:
        set_csrf_cookie(response, value, secure)
