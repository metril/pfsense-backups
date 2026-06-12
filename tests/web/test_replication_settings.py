"""Replication settings endpoint regressions.

v0.47.0 shipped a 500 on GET /api/settings for any deployment without a
``replication_settings`` row: the reader built a *transient*
``ReplicationSettings(id=1)`` whose fields are all None (mapped_column
defaults only apply at INSERT). Covers: missing-row defaults, the
secret sentinel round-trip, and the enable-without-password refusal.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pfsense_shared.crypto import Crypto
from pfsense_shared.models import Base
from web.dependencies import get_current_user
from web.routers import settings_router

from .conftest import TEST_USER


@pytest_asyncio.fixture
async def settings_client() -> AsyncIterator[AsyncClient]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app = FastAPI()
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app.state.crypto = Crypto(Fernet.generate_key())
    app.include_router(settings_router.router)
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await engine.dispose()


async def test_get_all_without_seeded_row_returns_defaults(settings_client) -> None:
    """No replication_settings row at all (pre-seed) → defaults, not 500."""
    r = await settings_client.get("/api/settings")
    assert r.status_code == 200
    repl = r.json()["replication"]
    assert repl["enabled"] is False
    assert repl["kind"] == "s3"
    assert repl["encrypt_plaintext"] is True
    assert repl["double_encrypt"] is False
    assert repl["mirror_deletes"] is False
    assert repl["base_path"] == "pfsense-backups"
    assert repl["sftp_port"] == 22


async def test_put_then_get_round_trips_with_sentinel(settings_client) -> None:
    r = await settings_client.put(
        "/api/settings/replication",
        json={
            "enabled": True,
            "kind": "s3",
            "s3_bucket": "bkt",
            "replication_password": "super-secret",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["enabled"] is True
    assert body["s3_bucket"] == "bkt"
    # Secret comes back as the sentinel, never plaintext.
    assert body["replication_password"] == "__set__"

    r2 = await settings_client.get("/api/settings")
    assert r2.json()["replication"]["replication_password"] == "__set__"


async def test_enable_without_password_is_refused(settings_client) -> None:
    r = await settings_client.put(
        "/api/settings/replication",
        json={"enabled": True, "kind": "s3", "s3_bucket": "bkt"},
    )
    assert r.status_code == 400
    assert "password" in r.json()["detail"]
