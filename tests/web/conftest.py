"""Shared fixtures for FastAPI endpoint tests.

Builds a minimal FastAPI app that mounts only the router under test,
swaps in an in-memory SQLite (via aiosqlite), a freshly-generated
Fernet-backed ``Crypto``, and a fixed "logged-in" user via dependency
override. A temp directory serves as the on-disk backup store so
routes that read ``<Backup>.path`` get real bytes.

Keep the fixtures narrow: each test opts in to the pieces it needs
(``client``, ``seed_backup``, ``seed_encrypted_backup``) so what's
under test stays obvious on the page.
"""

from __future__ import annotations

import gzip
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from starlette.middleware.sessions import SessionMiddleware

from pfsense_shared.crypto import Crypto
from pfsense_shared.models import AuditLog, Backup, Base, Instance
from pfsense_shared.pfsense_crypto import encrypt_pfsense_backup
from web.dependencies import get_current_user
from web.routers import backups as backups_router

TEST_USER = {"email": "tester@example.com", "name": "Tester"}

# A tiny but legitimate config.xml — enough to exercise every parsed
# section the tests care about (system, firewall rule, a cert blob).
# Stored as a raw Python string so tests can tweak it easily.
SAMPLE_XML = """<?xml version="1.0"?>
<pfsense>
  <version>21.9</version>
  <system>
    <hostname>gw-test</hostname>
    <domain>lan.example</domain>
    <timezone>UTC</timezone>
  </system>
  <filter>
    <rule>
      <tracker>1</tracker>
      <type>pass</type>
      <interface>lan</interface>
      <descr>allow lan</descr>
    </rule>
  </filter>
</pfsense>
""".strip()


@pytest.fixture
def sample_xml_bytes() -> bytes:
    return SAMPLE_XML.encode()


@pytest_asyncio.fixture
async def app_and_session(
    tmp_path: Path,
) -> AsyncIterator[tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto]]:
    """Minimal app with in-memory SQLite + Fernet crypto + logged-in user.

    ``tmp_path`` is used as the working dir for backup-file placement so
    each test gets its own clean store.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    crypto = Crypto(Fernet.generate_key())

    app = FastAPI()
    # SessionMiddleware is required for request.session access in
    # get_current_user's real implementation (used by the no-auth test).
    app.add_middleware(SessionMiddleware, secret_key="test-secret-not-real")
    app.state.session_factory = session_factory
    app.state.crypto = crypto
    # IPC + event bus aren't used by /parsed or /diff/pair/parsed — set
    # to None so any accidental use raises loudly.
    app.state.ipc_client = None
    app.state.event_bus = None

    app.include_router(backups_router.router)

    # Logged-in stub — real auth middleware isn't mounted here.
    app.dependency_overrides[get_current_user] = lambda: TEST_USER

    try:
        yield app, session_factory, crypto
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def client(
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
) -> AsyncIterator[AsyncClient]:
    app, _, _ = app_and_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _seed_instance(session_factory: async_sessionmaker[AsyncSession]) -> Instance:
    async with session_factory() as s:
        inst = Instance(
            name="gw-test",
            url="https://gw.test",
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
        return inst


async def _seed_backup_row(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    instance_id: int,
    path: Path,
    encrypted: bool = False,
    encrypt_password_ct: bytes | None = None,
    compressed: bool = False,
) -> Backup:
    async with session_factory() as s:
        row = Backup(
            instance_id=instance_id,
            started_at=datetime(2026, 4, 1, tzinfo=UTC),
            finished_at=datetime(2026, 4, 1, tzinfo=UTC),
            duration_seconds=1.0,
            filename=path.name,
            path=str(path),
            size_bytes=path.stat().st_size if path.exists() else 0,
            compressed=compressed,
            success=True,
            encrypted=encrypted,
            encrypt_password_ct=encrypt_password_ct,
        )
        s.add(row)
        await s.commit()
        await s.refresh(row)
        return row


@pytest_asyncio.fixture
async def seed_plain_backup(
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
    sample_xml_bytes: bytes,
) -> int:
    """Plain (unencrypted) backup file on disk + DB row. Returns backup id."""
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)
    path = tmp_path / "daily_gw-test_2026.xml"
    path.write_bytes(sample_xml_bytes)
    row = await _seed_backup_row(
        session_factory, instance_id=inst.id, path=path, encrypted=False
    )
    return row.id


@pytest_asyncio.fixture
async def seed_encrypted_backup(
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
    sample_xml_bytes: bytes,
) -> tuple[int, str]:
    """Encrypted backup file on disk + DB row. Returns (backup_id, password).

    The password is stored as Fernet-ciphertext in ``encrypt_password_ct``
    (matching prod), and the file bytes are produced with the real
    ``encrypt_pfsense_backup`` helper so the decrypt path exercises the
    same KDF + cipher the worker uses.
    """
    _, session_factory, crypto = app_and_session
    inst = await _seed_instance(session_factory)

    backup_password = "t3st-pass-phrase-abcXYZ"
    ciphertext = encrypt_pfsense_backup(sample_xml_bytes, backup_password)

    path = tmp_path / "daily_gw-test_2026.enc.xml"
    path.write_bytes(ciphertext)

    row = await _seed_backup_row(
        session_factory,
        instance_id=inst.id,
        path=path,
        encrypted=True,
        encrypt_password_ct=crypto.encrypt(backup_password),
    )
    return row.id, backup_password


@pytest_asyncio.fixture
async def seed_compressed_plain_backup(
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
    sample_xml_bytes: bytes,
) -> int:
    """Gzipped plain backup — exercises the gzip path in _decrypt_row_content."""
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)
    path = tmp_path / "daily_gw-test_2026.xml.gz"
    with gzip.open(path, "wb") as gz:
        gz.write(sample_xml_bytes)
    row = await _seed_backup_row(
        session_factory,
        instance_id=inst.id,
        path=path,
        encrypted=False,
        compressed=True,
    )
    return row.id


async def count_audit_entries(
    session_factory: async_sessionmaker[AsyncSession],
    action: str,
    resource: str,
) -> int:
    """Count audit log rows matching a filter. Used to assert that
    decrypt-path reads are logged."""
    from sqlalchemy import func, select

    async with session_factory() as s:
        stmt = (
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == action)
            .where(AuditLog.resource == resource)
        )
        result = await s.execute(stmt)
        return int(result.scalar_one())
