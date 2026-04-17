"""AuthRequiredMiddleware: enforces a session cookie on protected routes.

Allowlist matches anything the browser needs to bootstrap + the auth endpoints.
API requests without a session return 401 JSON; HTML requests get a 302 to /login.
Also emits CSRF-protection checks for mutating HTTP methods.
"""

from __future__ import annotations

import logging
import re
import secrets
from collections.abc import Awaitable, Callable

from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

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


def _is_public(path: str) -> bool:
    return any(p.search(path) for p in _PUBLIC_PATTERNS)


def _wants_json(request: Request) -> bool:
    if request.url.path.startswith("/api/"):
        return True
    return "application/json" in request.headers.get("accept", "")


class AuthRequiredMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # CSRF cookie is ensured on every response so the SPA can pick it up on first GET.
        needs_csrf_cookie = CSRF_COOKIE not in request.cookies
        csrf_value = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)

        path = request.url.path
        if not _is_public(path):
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
                self._ensure_csrf_cookie(response, csrf_value, needs_csrf_cookie)
                return response

            # CSRF: double-submit check on mutating requests (outside /api/auth/).
            exempt = any(path.startswith(p) for p in _CSRF_EXEMPT_PATHS)
            if request.method in _MUTATING and not exempt:
                sent = request.headers.get(CSRF_HEADER)
                if not sent or sent != csrf_value:
                    log.warning("CSRF check failed for %s %s", request.method, path)
                    response = JSONResponse(
                        status_code=403, content={"detail": "CSRF token missing or invalid"}
                    )
                    self._ensure_csrf_cookie(response, csrf_value, needs_csrf_cookie)
                    return response

        response = await call_next(request)
        self._ensure_csrf_cookie(response, csrf_value, needs_csrf_cookie)
        return response

    @staticmethod
    def _ensure_csrf_cookie(response: Response, value: str, needs_cookie: bool) -> None:
        if not needs_cookie:
            return
        response.set_cookie(
            key=CSRF_COOKIE,
            value=value,
            httponly=False,   # SPA must read it to echo via X-CSRF-Token
            secure=True,
            samesite="lax",
            path="/",
        )
