"""Hardening regressions: no absolute paths in responses, zip-size cap,
and the CSRF cookie's ``secure`` flag respecting dev_mode.

The CSRF tests mount the auth router on a minimal app with a stub
``app.state.settings`` — production puts a real ``Settings`` object
there; only ``dev_mode`` matters to the cookie flag.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.middleware.sessions import SessionMiddleware

from web.routers import auth as auth_router


@pytest.mark.asyncio
async def test_get_backup_response_has_no_filesystem_path(
    client, seed_plain_backup
) -> None:
    resp = await client.get(f"/api/backups/{seed_plain_backup}")
    assert resp.status_code == 200
    body = resp.json()
    assert "path" not in body
    assert body["filename"]  # the UI-facing field stays


@pytest.mark.asyncio
async def test_download_zip_rejects_oversized_id_list(client) -> None:
    resp = await client.post(
        "/api/backups/download-zip", json={"ids": list(range(1, 202))}
    )
    assert resp.status_code == 422
    assert "too many ids" in resp.json()["detail"]


def _auth_app(dev_mode: bool) -> FastAPI:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret-not-real")
    app.state.settings = SimpleNamespace(dev_mode=dev_mode)
    app.include_router(auth_router.router)
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dev_mode", "expect_secure"), [(True, False), (False, True)]
)
async def test_csrf_cookie_secure_flag_respects_dev_mode(
    dev_mode: bool, expect_secure: bool
) -> None:
    transport = ASGITransport(app=_auth_app(dev_mode))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/auth/csrf")
    assert resp.status_code == 200
    set_cookie = next(
        v
        for k, v in resp.headers.multi_items()
        if k.lower() == "set-cookie" and v.startswith("csrftoken=")
    )
    assert ("Secure" in set_cookie) is expect_secure
