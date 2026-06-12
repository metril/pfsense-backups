"""F7 API tokens: bearer auth through the real AuthRequiredMiddleware.

Builds an app with SessionMiddleware + AuthRequiredMiddleware + the
tokens router + a tiny protected echo router, so the tests exercise the
exact auth path production uses:

- session client mints a token (CSRF double-submit honoured);
- bearer GET with no session cookie → 200;
- read-scope write → 403; write-scope POST without CSRF → 200;
- disabled / deleted / expired tokens → 401;
- a bearer caller can never touch /api/tokens.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest_asyncio
from fastapi import APIRouter, FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.middleware.sessions import SessionMiddleware

from pfsense_shared.models import ApiToken, Base
from web.dependencies import CurrentUser
from web.middleware import CSRF_COOKIE, CSRF_HEADER, AuthRequiredMiddleware
from web.routers import tokens as tokens_router
from web.services.token_auth import clear_cache

echo = APIRouter(prefix="/api/echo")


@echo.get("")
async def echo_get(user: CurrentUser) -> dict:
    return {"actor": user["email"]}


@echo.post("")
async def echo_post(user: CurrentUser) -> dict:
    return {"actor": user["email"]}


auth_stub = APIRouter(prefix="/api/auth")


@auth_stub.post("/test-login")
async def stub_login(request: Request) -> dict:
    request.session["user"] = {"email": "admin@example.test", "name": "Admin"}
    return {"ok": True}


@pytest_asyncio.fixture
async def token_app() -> AsyncIterator[tuple[FastAPI, async_sessionmaker]]:
    clear_cache()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    app.add_middleware(AuthRequiredMiddleware)
    app.add_middleware(SessionMiddleware, secret_key="test-secret-not-real")
    app.state.session_factory = session_factory
    app.state.settings = SimpleNamespace(dev_mode=True)
    app.include_router(auth_stub)
    app.include_router(tokens_router.router)
    app.include_router(echo)
    try:
        yield app, session_factory
    finally:
        await engine.dispose()


async def _session_client(app: FastAPI) -> AsyncClient:
    """Client logged in via session, with CSRF header pre-armed."""
    c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    r = await c.post("/api/auth/test-login")
    assert r.status_code == 200
    csrf = c.cookies.get(CSRF_COOKIE)
    assert csrf
    c.headers[CSRF_HEADER] = csrf
    return c


async def _mint(app: FastAPI, scope: str = "read", **kw) -> tuple[str, int]:
    sc = await _session_client(app)
    r = await sc.post("/api/tokens", json={"name": f"tok-{scope}", "scope": scope, **kw})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["token"].startswith("pfsb_")
    await sc.aclose()
    return body["token"], body["id"]


def _bearer(app: FastAPI, token: str) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    )


async def test_bearer_get_without_session(token_app) -> None:
    app, _ = token_app
    token, _id = await _mint(app, "read")
    async with _bearer(app, token) as c:
        r = await c.get("/api/echo")
    assert r.status_code == 200
    assert r.json()["actor"] == "token:tok-read"


async def test_read_scope_rejects_writes(token_app) -> None:
    app, _ = token_app
    token, _id = await _mint(app, "read")
    async with _bearer(app, token) as c:
        r = await c.post("/api/echo")
    assert r.status_code == 403


async def test_write_scope_post_skips_csrf(token_app) -> None:
    app, _ = token_app
    token, _id = await _mint(app, "write")
    async with _bearer(app, token) as c:
        r = await c.post("/api/echo")  # no CSRF header, no cookie
    assert r.status_code == 200


async def test_disabled_token_rejected(token_app) -> None:
    app, _ = token_app
    token, token_id = await _mint(app, "read")
    sc = await _session_client(app)
    r = await sc.patch(f"/api/tokens/{token_id}", json={"enabled": False})
    assert r.status_code == 200
    await sc.aclose()
    async with _bearer(app, token) as c:
        r = await c.get("/api/echo")
    assert r.status_code == 401


async def test_expired_token_rejected(token_app) -> None:
    app, session_factory = token_app
    token, token_id = await _mint(app, "read", expires_in_days=1)
    # Backdate the expiry directly.
    async with session_factory() as s:
        row = (
            await s.execute(select(ApiToken).where(ApiToken.id == token_id))
        ).scalar_one()
        row.expires_at = datetime.now(UTC) - timedelta(hours=1)
        await s.commit()
    clear_cache()
    async with _bearer(app, token) as c:
        r = await c.get("/api/echo")
    assert r.status_code == 401


async def test_garbage_bearer_rejected(token_app) -> None:
    app, _ = token_app
    async with _bearer(app, "pfsb_not-a-real-token") as c:
        r = await c.get("/api/echo")
    assert r.status_code == 401


async def test_token_cannot_manage_tokens(token_app) -> None:
    app, _ = token_app
    token, _id = await _mint(app, "write")
    async with _bearer(app, token) as c:
        r_list = await c.get("/api/tokens")
        r_mint = await c.post(
            "/api/tokens", json={"name": "evil", "scope": "write"}
        )
    assert r_list.status_code == 403
    assert r_mint.status_code == 403


async def test_secret_never_listed(token_app) -> None:
    app, _ = token_app
    await _mint(app, "read")
    sc = await _session_client(app)
    r = await sc.get("/api/tokens")
    await sc.aclose()
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert "token" not in rows[0]
    assert rows[0]["prefix"].startswith("pfsb_")
