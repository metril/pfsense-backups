"""OIDC auth endpoints: login, callback, logout, me, csrf."""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

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
    # authlib fetches the IdP's OIDC discovery document on first call and
    # stores state/nonce in the session. Any of: network unreachable,
    # TLS cert mismatch, httpx timeout, or session-cookie write failure
    # lands here. Log the traceback explicitly so operators don't have to
    # guess from a 500 response with no context.
    try:
        return await oauth.oidc.authorize_redirect(request, redirect_url)
    except Exception:
        issuer = request.app.state.settings.oidc_issuer
        log.exception("OIDC authorize_redirect failed (issuer=%s)", issuer)
        return RedirectResponse(url="/login?error=authorize_redirect_failed", status_code=302)


@router.get("/callback")
@limiter.limit(login_limit)
async def callback(request: Request) -> Response:
    oauth = request.app.state.oauth
    settings = request.app.state.settings
    try:
        token = await oauth.oidc.authorize_access_token(request)
    except Exception:
        log.exception("OIDC token exchange failed")
        # L9: redirect the browser to /login with an error query-param so the
        # SPA can render a user-friendly message instead of raw JSON.
        return RedirectResponse(url="/login?error=oidc_exchange_failed", status_code=302)

    # Everything past the token exchange needs its own guard: userinfo
    # fetches, claim coercion, session writes can all raise. An uncaught
    # exception here produces an opaque "Internal Server Error" page with
    # the traceback buried in uvicorn's stderr. log.exception puts the
    # traceback on the root logger so it lands in `docker logs` alongside
    # the rest of our app output.
    try:
        claims = token.get("userinfo")
        if not claims:
            try:
                claims = await oauth.oidc.userinfo(token=token)
            except Exception:
                log.exception("OIDC userinfo fetch failed; no id_token claims to fall back on")
                return RedirectResponse(url="/login?error=userinfo_failed", status_code=302)

        user = user_from_claims(dict(claims))
        if user is None:
            log.warning("OIDC claims had no usable email: %r", dict(claims))
            return RedirectResponse(url="/login?error=no_email", status_code=302)

        allowed = {e.lower() for e in settings.oidc_allowed_emails}
        if user["email"].lower() not in allowed:
            log.warning("Login denied (not on allowlist): %s", user["email"])
            return RedirectResponse(url="/login?error=access_denied", status_code=302)

        request.session["user"] = user
        log.info("Login OK: %s", user["email"])
        return RedirectResponse(url="/", status_code=302)
    except Exception:
        log.exception("OIDC callback pipeline failure")
        return RedirectResponse(url="/login?error=server_error", status_code=302)


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
