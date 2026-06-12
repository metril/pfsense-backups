"""OIDC auth endpoints: login, callback, logout, me, csrf.

Uses our own PyJWT-based `OIDCProvider` (web/services/oidc.py) rather than
authlib. State + PKCE verifier + nonce are stashed in the server-side
session (Starlette SessionMiddleware, signed cookie) keyed by state so the
callback can retrieve them.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

from ..dependencies import CurrentUser
from ..middleware import CSRF_COOKIE, CSRF_HEADER, csrf_cookie_secure, set_csrf_cookie
from ..services.oidc import generate_pkce, user_from_claims
from ..services.rate_limit import limiter, login_limit

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_OIDC_STATE_KEY = "oidc_pending"


@router.get("/login")
@limiter.limit(login_limit)
async def login(request: Request) -> Response:
    provider = request.app.state.oidc_provider
    redirect_uri = request.app.state.settings.oidc_redirect_url

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    code_verifier, code_challenge = generate_pkce()

    # Stash the per-request secrets in the signed-cookie session so the
    # callback can validate state + exchange the code.
    request.session[_OIDC_STATE_KEY] = {
        "state": state,
        "nonce": nonce,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
    }

    try:
        auth_url = await provider.authorization_url(
            state=state,
            code_challenge=code_challenge,
            nonce=nonce,
            redirect_uri=redirect_uri,
        )
    except Exception:
        issuer = request.app.state.settings.oidc_issuer
        log.exception("OIDC authorization_url failed (issuer=%s)", issuer)
        return RedirectResponse(
            url="/login?error=authorize_redirect_failed", status_code=302
        )

    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/callback")
@limiter.limit(login_limit)
async def callback(request: Request) -> Response:
    provider = request.app.state.oidc_provider
    settings = request.app.state.settings

    pending = request.session.pop(_OIDC_STATE_KEY, None)
    if not pending:
        log.warning("OIDC callback with no pending state — session expired or lost")
        return RedirectResponse(url="/login?error=no_pending_state", status_code=302)

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state or state != pending.get("state"):
        log.warning("OIDC callback state mismatch or missing code")
        return RedirectResponse(url="/login?error=state_mismatch", status_code=302)

    try:
        tokens = await provider.exchange_code(
            code=code,
            code_verifier=pending["code_verifier"],
            redirect_uri=pending["redirect_uri"],
        )
    except Exception:
        log.exception("OIDC token exchange failed")
        return RedirectResponse(url="/login?error=oidc_exchange_failed", status_code=302)

    id_token = tokens.get("id_token")
    if not id_token:
        log.warning("OIDC token response missing id_token: keys=%s", list(tokens))
        return RedirectResponse(url="/login?error=no_id_token", status_code=302)

    try:
        claims = await provider.validate_id_token(id_token, nonce=pending["nonce"])
    except Exception:
        log.exception("OIDC id_token validation failed")
        return RedirectResponse(url="/login?error=id_token_invalid", status_code=302)

    user = user_from_claims(claims)
    if user is None:
        log.warning("OIDC claims had no usable email: %r", claims)
        return RedirectResponse(url="/login?error=no_email", status_code=302)

    allowed = {e.lower() for e in settings.oidc_allowed_emails}
    if user["email"].lower() not in allowed:
        log.warning("Login denied (not on allowlist): %s", user["email"])
        return RedirectResponse(url="/login?error=access_denied", status_code=302)

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
        set_csrf_cookie(response, token, csrf_cookie_secure(request))
    return {"csrf": token, "header": CSRF_HEADER}


@router.get("/status")
async def auth_status(request: Request) -> dict[str, Any]:
    """Lightweight auth probe — returns whether the caller has a session."""
    user = request.session.get("user")
    return {"authenticated": bool(user), "email": user["email"] if user else None}
