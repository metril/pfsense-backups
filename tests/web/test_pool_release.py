"""v0.45.1 stress test — verify that hot endpoints release their DB
session before doing heavy decrypt+parse+diff work.

The reproducer pins the pool at ``size=2, overflow=0`` so concurrent
requests MUST hand connections back quickly or they'll time out. Pre-
fix, ``/diff/pair/parsed`` held its session through the full parse
chain and 10 concurrent requests would exhaust the 2-slot pool before
any of them finished. Post-fix the session is closed before the parse,
so each request only holds a slot for the initial 2× row load and
then releases. The pool sustains 10 concurrent callers fine.

These tests intentionally use a file-backed SQLite (not ``:memory:``)
+ ``QueuePool`` so the pool config actually takes effect — SQLAlchemy
swaps the pool class to SingletonThreadPool for in-memory dbs.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import AsyncAdaptedQueuePool
from starlette.middleware.sessions import SessionMiddleware

from pfsense_shared.crypto import Crypto
from pfsense_shared.models import Backup, Base, Instance
from web.dependencies import get_current_user
from web.routers import backups as backups_router

from .conftest import SAMPLE_XML, TEST_USER

# Pool tight enough that any session held across the parse would block
# the test. The fix's whole point is that sessions are released before
# the slow asyncio.to_thread work.
TIGHT_POOL_SIZE = 2
TIGHT_OVERFLOW = 0


@pytest_asyncio.fixture
async def tight_pool_app(
    tmp_path: Path,
) -> AsyncIterator[tuple[FastAPI, async_sessionmaker[AsyncSession], int, int]]:
    """App wired against a file-backed SQLite with a 2-slot pool, two
    seeded plain backups, and a logged-in stub user. Yields
    ``(app, session_factory, backup_a_id, backup_b_id)``.
    """
    db_path = tmp_path / "stress.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=AsyncAdaptedQueuePool,
        pool_size=TIGHT_POOL_SIZE,
        max_overflow=TIGHT_OVERFLOW,
        # Without this, the in-test default pool_timeout (30s) means a
        # pre-fix regression would just hang for half a minute. Cap it
        # short so the test fails fast on slot starvation.
        pool_timeout=5.0,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    crypto = Crypto(Fernet.generate_key())

    # Two plain backups on disk so /diff/pair/parsed has real content
    # to parse. Identical XML so the diff result is small but the
    # parse path still does the full work.
    a_path = tmp_path / "a.xml"
    b_path = tmp_path / "b.xml"
    a_path.write_bytes(SAMPLE_XML.encode())
    b_path.write_bytes(SAMPLE_XML.encode())

    async with session_factory() as s:
        inst = Instance(
            name="gw-stress",
            url="https://gw.stress",
            username_ct=b"x",
            password_ct=b"x",
            subfolder=None,
            backup_prefix="daily",
            verify_ssl=False,
            timeout_seconds=30,
            enabled=True,
            retention_count=10,
        )
        s.add(inst)
        await s.commit()
        await s.refresh(inst)

        a_row = Backup(
            instance_id=inst.id,
            started_at=datetime(2026, 5, 1, tzinfo=UTC),
            finished_at=datetime(2026, 5, 1, tzinfo=UTC),
            duration_seconds=1.0,
            filename=a_path.name,
            path=str(a_path),
            size_bytes=a_path.stat().st_size,
            compressed=False,
            success=True,
            encrypted=False,
        )
        b_row = Backup(
            instance_id=inst.id,
            started_at=datetime(2026, 5, 2, tzinfo=UTC),
            finished_at=datetime(2026, 5, 2, tzinfo=UTC),
            duration_seconds=1.0,
            filename=b_path.name,
            path=str(b_path),
            size_bytes=b_path.stat().st_size,
            compressed=False,
            success=True,
            encrypted=False,
        )
        s.add_all([a_row, b_row])
        await s.commit()
        await s.refresh(a_row)
        await s.refresh(b_row)
        a_id, b_id = a_row.id, b_row.id

    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret-not-real")
    app.state.session_factory = session_factory
    app.state.crypto = crypto
    app.state.ipc_client = None
    app.state.event_bus = None
    app.include_router(backups_router.router)
    app.dependency_overrides[get_current_user] = lambda: TEST_USER

    try:
        yield app, session_factory, a_id, b_id
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def tight_pool_client(
    tight_pool_app: tuple[FastAPI, async_sessionmaker[AsyncSession], int, int],
) -> AsyncIterator[AsyncClient]:
    app, _, _, _ = tight_pool_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_diff_pair_parsed_does_not_exhaust_pool(
    tight_pool_client: AsyncClient,
    tight_pool_app: tuple[FastAPI, async_sessionmaker[AsyncSession], int, int],
) -> None:
    """10 concurrent requests against a 2-slot pool — all must
    complete within a generous timeout. Pre-v0.45.1 the session was
    held through the parse and this hangs until the 30s pool-timeout
    fires on the 3rd+ request.
    """
    _, _, a_id, b_id = tight_pool_app
    n = 10
    requests = [
        tight_pool_client.get(
            f"/api/backups/diff/pair/parsed?a={a_id}&b={b_id}"
        )
        for _ in range(n)
    ]
    responses = await asyncio.wait_for(asyncio.gather(*requests), timeout=15.0)
    assert all(r.status_code == 200 for r in responses), [
        (r.status_code, r.text[:200]) for r in responses if r.status_code != 200
    ]


async def test_parsed_does_not_exhaust_pool(
    tight_pool_client: AsyncClient,
    tight_pool_app: tuple[FastAPI, async_sessionmaker[AsyncSession], int, int],
) -> None:
    """Same shape as the pair-diff test, but against the single-backup
    ``/parsed`` endpoint."""
    _, _, a_id, _ = tight_pool_app
    n = 10
    requests = [
        tight_pool_client.get(f"/api/backups/{a_id}/parsed") for _ in range(n)
    ]
    responses = await asyncio.wait_for(asyncio.gather(*requests), timeout=15.0)
    assert all(r.status_code == 200 for r in responses), [
        (r.status_code, r.text[:200]) for r in responses if r.status_code != 200
    ]


async def test_diff_pair_raw_does_not_exhaust_pool(
    tight_pool_client: AsyncClient,
    tight_pool_app: tuple[FastAPI, async_sessionmaker[AsyncSession], int, int],
) -> None:
    """Raw-XML pair-diff endpoint also releases the session before
    file reads."""
    _, _, a_id, b_id = tight_pool_app
    n = 10
    requests = [
        tight_pool_client.get(f"/api/backups/diff/pair?a={a_id}&b={b_id}")
        for _ in range(n)
    ]
    responses = await asyncio.wait_for(asyncio.gather(*requests), timeout=15.0)
    assert all(r.status_code == 200 for r in responses), [
        (r.status_code, r.text[:200]) for r in responses if r.status_code != 200
    ]
