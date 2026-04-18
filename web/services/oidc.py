"""Authlib-backed OIDC client. One provider, discovery-based config."""

from __future__ import annotations

import logging
from typing import Any

from authlib.integrations.starlette_client import OAuth

log = logging.getLogger(__name__)


def make_oauth(
    *, issuer: str, client_id: str, client_secret: str, name: str = "oidc"
) -> OAuth:
    """Return an Authlib OAuth registry with one provider named ``oidc``.

    Relies on the standard OIDC discovery document at
    ``{issuer}/.well-known/openid-configuration``.
    """
    oauth = OAuth()
    oauth.register(
        name=name,
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=f"{issuer.rstrip('/')}/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    log.info("OIDC registered: issuer=%s client_id=%s", issuer, client_id)
    return oauth


def user_from_claims(claims: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the session user payload from an ID-token claims dict.

    Defensive about the `email` shape: some IdPs return a list-of-string
    (Authelia betas did this). Anything we can't coerce to a non-empty
    string yields None so the caller redirects rather than 500s.
    """
    raw = claims.get("email")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if not isinstance(raw, str):
        return None
    email = raw.strip().lower()
    if not email:
        return None
    return {
        "email": email,
        "name": claims.get("name") or claims.get("preferred_username") or email,
        "picture": claims.get("picture"),
    }
