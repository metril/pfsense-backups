"""OIDC auth endpoints: login, callback, logout, me, csrf."""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from ..dependencies import CurrentUser
from ..middleware import CSRF_COOKIE, CSRF_HEADER
from ..services.oidc import user_from_claims
from ..services.rate_limit import limiter, login_limit

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/login")
@limiter.limit(login_limit)
async def login(request: Request) -> Response:
    oauth = request.app.state.oauth
    redirect_url = request.app.state.settings.oidc_redirect_url
    return await oauth.oidc.authorize_redirect(request, redirect_url)


@router.get("/callback")
@limiter.limit(login_limit)
async def callback(request: Request) -> Response:
    oauth = request.app.state.oauth
    settings = request.app.state.settings
    try:
        token = await oauth.oidc.authorize_access_token(request)
    except Exception as exc:
        log.error("OIDC callback failed: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "OIDC exchange failed"},
        )

    claims = token.get("userinfo") or await oauth.oidc.userinfo(token=token)
    user = user_from_claims(dict(claims))
    if user is None:
        return JSONResponse(status_code=403, content={"detail": "no email in ID token"})

    allowed = {e.lower() for e in settings.oidc_allowed_emails}
    if user["email"].lower() not in allowed:
        log.warning("Login denied (not on allowlist): %s", user["email"])
        return JSONResponse(
            status_code=403,
            content={"detail": f"access denied for {user['email']}"},
        )

    request.session["user"] = user
    log.info("Login OK: %s", user["email"])
    return RedirectResponse(url="/", status_code=302)


@router.post("/logout")
async def logout(request: Request) -> dict[str, Any]:
    request.session.clear()
    return {"ok": True}


@router.get("/me")
async def me(user: CurrentUser) -> dict[str, Any]:
    return {"email": user["email"], "name": user.get("name"), "picture": user.get("picture")}


@router.get("/csrf")
async def csrf(request: Request, response: Response) -> dict[str, str]:
    """Return the current CSRF token (from the `csrftoken` cookie, generating it on first call)."""
    token = request.cookies.get(CSRF_COOKIE)
    if not token:
        token = secrets.token_urlsafe(32)
        response.set_cookie(
            key=CSRF_COOKIE,
            value=token,
            httponly=False,
            secure=True,
            samesite="lax",
            path="/",
        )
    return {"csrf": token, "header": CSRF_HEADER}


@router.get("/status")
async def auth_status(request: Request) -> dict[str, Any]:
    """Lightweight auth probe — returns whether the caller has a session."""
    user = request.session.get("user")
    return {"authenticated": bool(user), "email": user["email"] if user else None}
