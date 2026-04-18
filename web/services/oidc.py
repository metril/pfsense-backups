"""OIDC client: discovery, PKCE authorization, code exchange, id_token verify.

Modeled on a working PyJWT+httpx implementation that's proven against Authentik,
since the previous authlib-based path hit "Invalid key set format" and
"UnsupportedAlgorithm" against the same IdP. PyJWT's PyJWKClient handles the
JWKS fetch/parse and gives us direct control over which JWT algorithms to
accept.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWK, PyJWKSet, get_unverified_header

log = logging.getLogger(__name__)


_ACCEPTED_ID_TOKEN_ALGS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "EdDSA"]


@dataclass
class OIDCProvider:
    issuer: str
    client_id: str
    client_secret: str
    _discovery: dict[str, Any] | None = field(default=None, init=False, repr=False)

    async def discover(self) -> dict[str, Any]:
        """Fetch + cache the OIDC discovery document."""
        if self._discovery is not None:
            return self._discovery
        url = self.issuer.rstrip("/") + "/.well-known/openid-configuration"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            self._discovery = resp.json()
        log.info(
            "OIDC discovery loaded: issuer=%s client_id=%s",
            self.issuer,
            self.client_id,
        )
        return self._discovery

    async def authorization_url(
        self, *, state: str, code_challenge: str, nonce: str, redirect_uri: str
    ) -> str:
        d = await self.discover()
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{d['authorization_endpoint']}?{urlencode(params)}"

    async def exchange_code(
        self, *, code: str, code_verifier: str, redirect_uri: str
    ) -> dict[str, Any]:
        d = await self.discover()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                d["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code_verifier": code_verifier,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def validate_id_token(self, id_token: str, *, nonce: str) -> dict[str, Any]:
        """Verify the id_token signature via JWKS and assert nonce matches."""
        d = await self.discover()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(d["jwks_uri"])
            resp.raise_for_status()
            jwks_data = resp.json()

        jwk_set = PyJWKSet.from_dict(jwks_data)
        kid = get_unverified_header(id_token).get("kid")
        if kid is None:
            # Single-key JWKS, pick the first.
            if not jwk_set.keys:
                raise ValueError("JWKS contains no signing keys")
            signing_key: PyJWK = jwk_set.keys[0]
        else:
            try:
                signing_key = jwk_set[kid]
            except KeyError as exc:
                raise ValueError(f"No signing key found for kid={kid!r}") from exc

        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=_ACCEPTED_ID_TOKEN_ALGS,
            audience=self.client_id,
            issuer=d.get("issuer"),
            options={"require": ["exp", "iat", "sub"]},
        )

        if claims.get("nonce") != nonce:
            raise ValueError("id_token nonce mismatch")
        return claims


def make_oidc_provider(
    *, issuer: str, client_id: str, client_secret: str
) -> OIDCProvider:
    """Factory kept for parity with the previous authlib-based API surface."""
    return OIDCProvider(
        issuer=issuer, client_id=client_id, client_secret=client_secret
    )


def user_from_claims(claims: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the session user payload from an ID-token claims dict.

    Defensive about the ``email`` shape: some IdPs return a list-of-string
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


def generate_pkce() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge)``. S256 challenge method."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge
