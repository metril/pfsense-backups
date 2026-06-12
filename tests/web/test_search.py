"""F4 global search: value-substring + anchor-id matching, LIKE
escaping, instance/kind filters, keyset pagination.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pfsense_shared.models import AnchorEvent, Backup, Base, Instance
from web.dependencies import get_current_user
from web.routers import search as search_router

from .conftest import TEST_USER


@pytest_asyncio.fixture
async def search_app() -> AsyncIterator[tuple[FastAPI, async_sessionmaker]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app = FastAPI()
    app.state.session_factory = session_factory
    app.include_router(search_router.router)
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    try:
        yield app, session_factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def search_client(search_app) -> AsyncIterator[AsyncClient]:
    app, _ = search_app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def _seed(session_factory) -> dict[str, int]:
    """Two instances; events with distinct values + anchors."""
    t0 = datetime(2026, 6, 1, tzinfo=UTC)
    async with session_factory() as s:
        ids: dict[str, int] = {}
        for name in ("gw-a", "gw-b"):
            inst = Instance(
                name=name, url=f"https://{name}.test",
                username_ct=b"x", password_ct=b"x", backup_prefix="daily",
            )
            s.add(inst)
            await s.flush()
            bkp = Backup(
                instance_id=inst.id, started_at=t0, finished_at=t0,
                duration_seconds=1.0, filename=f"{name}.xml",
                path=f"/tmp/{name}.xml", size_bytes=1, compressed=False,
                success=True, encrypted=False,
            )
            s.add(bkp)
            await s.flush()
            ids[name] = inst.id
            ids[f"{name}-backup"] = bkp.id

        def ev(inst_key: str, anchor: str, value, kind: str, hours: int) -> AnchorEvent:
            return AnchorEvent(
                instance_id=ids[inst_key],
                backup_id=ids[f"{inst_key}-backup"],
                prev_backup_id=None,
                anchor_id=anchor,
                occurred_at=t0 + timedelta(hours=hours),
                kind=kind,
                value_json=json.dumps(value),
            )

        alias_v1 = {"name": "mgmt_hosts", "address": "192.0.2.5"}
        alias_v2 = {"name": "mgmt_hosts", "address": "192.0.2.6"}
        s.add(ev("gw-a", "xref-alias-mgmt_hosts", alias_v1, "added", 1))
        s.add(ev("gw-a", "xref-alias-mgmt_hosts", alias_v2, "modified", 2))
        s.add(ev("gw-b", "xref-fwrule-100", {"descr": "allow 192.0.2.5 ssh"}, "added", 3))
        s.add(ev("gw-b", "field-system-hostname", "gw-100%-special", "modified", 4))
        await s.commit()
        return ids


async def test_value_substring_match_across_instances(search_client, search_app) -> None:
    _, session_factory = search_app
    await _seed(session_factory)
    r = await search_client.get("/api/search?q=192.0.2.5")
    assert r.status_code == 200
    body = r.json()
    assert body["has_more"] is False
    assert len(body["hits"]) == 2
    # Newest first.
    assert [h["instance_name"] for h in body["hits"]] == ["gw-b", "gw-a"]
    assert all("192.0.2.5" in h["excerpt"] for h in body["hits"])


async def test_anchor_id_match(search_client, search_app) -> None:
    _, session_factory = search_app
    await _seed(session_factory)
    r = await search_client.get("/api/search?q=mgmt_hosts")
    assert r.status_code == 200
    assert len(r.json()["hits"]) == 2
    assert {h["anchor_id"] for h in r.json()["hits"]} == {"xref-alias-mgmt_hosts"}


async def test_like_escape(search_client, search_app) -> None:
    _, session_factory = search_app
    await _seed(session_factory)
    # "100%" must match literally, not as "100<anything>".
    r = await search_client.get("/api/search?q=100%25-special")
    assert r.status_code == 200
    hits = r.json()["hits"]
    assert len(hits) == 1
    assert hits[0]["anchor_id"] == "field-system-hostname"
    # And a wildcard query that would match everything if unescaped.
    r2 = await search_client.get("/api/search?q=zz%25zz")
    assert r2.json()["hits"] == []


async def test_instance_and_kind_filters(search_client, search_app) -> None:
    _, session_factory = search_app
    ids = await _seed(session_factory)
    r = await search_client.get(f"/api/search?q=192.0.2&instance_id={ids['gw-a']}")
    assert {h["instance_name"] for h in r.json()["hits"]} == {"gw-a"}
    r2 = await search_client.get("/api/search?q=192.0.2&kind=modified")
    assert [h["kind"] for h in r2.json()["hits"]] == ["modified"]
    r3 = await search_client.get("/api/search?q=192.0.2&kind=bogus")
    assert r3.status_code == 422


async def test_keyset_pagination(search_client, search_app) -> None:
    _, session_factory = search_app
    await _seed(session_factory)
    r1 = await search_client.get("/api/search?q=192.0.2&limit=1")
    body1 = r1.json()
    assert len(body1["hits"]) == 1
    assert body1["has_more"] is True
    cursor = body1["hits"][0]["event_id"]
    r2 = await search_client.get(f"/api/search?q=192.0.2&limit=10&before_id={cursor}")
    body2 = r2.json()
    assert body2["has_more"] is False
    assert all(h["event_id"] < cursor for h in body2["hits"])


async def test_short_query_rejected(search_client) -> None:
    r = await search_client.get("/api/search?q=a")
    assert r.status_code == 422
    r2 = await search_client.get("/api/search")
    assert r2.status_code == 422


async def test_label_from_value_json(search_client, search_app) -> None:
    _, session_factory = search_app
    await _seed(session_factory)
    r = await search_client.get("/api/search?q=mgmt_hosts")
    labels = {h["label"] for h in r.json()["hits"]}
    assert labels == {"mgmt_hosts"}
