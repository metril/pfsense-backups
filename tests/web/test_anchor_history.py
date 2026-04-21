"""Integration tests for ``/api/backups/instance/{id}/anchor-history``.

The endpoint walks every successful backup for an instance and
resolves the requested anchor in each parsed config. Two load-bearing
behaviors are tested here because they'd be easy to regress
silently:

- The DB session is released BEFORE the decrypt+parse loop so the
  pool doesn't exhaust under concurrent blame-drawer opens.
- The plain row-snapshot type (``_BackupWalkRow``) is used in the
  walk instead of ORM instances — the thread can't safely touch a
  live ORM row.

The tests also cover the audit semantic (one ``view_decrypted`` per
drilled-in anchor when any backup is encrypted) and the transition
detection (``is_change`` for the first entry + every value change).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pfsense_shared.crypto import Crypto
from pfsense_shared.models import Backup
from pfsense_shared.pfsense_crypto import encrypt_pfsense_backup

from .conftest import _seed_instance, count_audit_entries


def _xml(hostname: str) -> bytes:
    """Sample config with a single, editable field so we can drive
    value changes across backups."""
    return (
        '<?xml version="1.0"?>\n'
        "<pfsense>\n"
        "  <version>21.9</version>\n"
        "  <system>\n"
        f"    <hostname>{hostname}</hostname>\n"
        "  </system>\n"
        "</pfsense>\n"
    ).encode()


@pytest.mark.usefixtures("client")
async def test_anchor_history_tracks_hostname_over_time(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
) -> None:
    """Three chronological backups with two hostname edits produce
    three entries; ``is_change`` fires on entry 0 (first-seen) +
    entries 1 & 2 (values differ from predecessor)."""
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)

    t0 = datetime(2026, 4, 1, tzinfo=UTC)
    for i, hostname in enumerate(["gw-a", "gw-b", "gw-c"]):
        p = tmp_path / f"daily_gw_{i}.xml"
        p.write_bytes(_xml(hostname))
        # Manually control started_at to keep the ordering deterministic.
        async with session_factory() as s:
            row = Backup(
                instance_id=inst.id,
                started_at=t0 + timedelta(days=i),
                finished_at=t0 + timedelta(days=i),
                duration_seconds=1.0,
                filename=p.name,
                path=str(p),
                size_bytes=p.stat().st_size,
                compressed=False,
                success=True,
                encrypted=False,
            )
            s.add(row)
            await s.commit()

    r = await client.get(
        f"/api/backups/instance/{inst.id}/anchor-history"
        "?anchor=field-system-hostname"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["anchor"] == "field-system-hostname"
    assert body["instance_id"] == inst.id
    entries = body["entries"]
    assert [e["value"] for e in entries] == ["gw-a", "gw-b", "gw-c"]
    # First-seen + two transitions = all three flagged as changes.
    assert [e["is_change"] for e in entries] == [True, True, True]


async def test_anchor_history_unchanged_runs_not_flagged(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
) -> None:
    """Consecutive backups with the same value: only the first is a
    change; subsequent ones have ``is_change=False`` so the drawer
    can collapse them as unchanged runs."""
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)

    t0 = datetime(2026, 4, 1, tzinfo=UTC)
    for i in range(3):
        p = tmp_path / f"daily_stable_{i}.xml"
        p.write_bytes(_xml("gw-stable"))
        async with session_factory() as s:
            row = Backup(
                instance_id=inst.id,
                started_at=t0 + timedelta(days=i),
                finished_at=t0 + timedelta(days=i),
                duration_seconds=1.0,
                filename=p.name,
                path=str(p),
                size_bytes=p.stat().st_size,
                compressed=False,
                success=True,
                encrypted=False,
            )
            s.add(row)
            await s.commit()

    r = await client.get(
        f"/api/backups/instance/{inst.id}/anchor-history"
        "?anchor=field-system-hostname"
    )
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert [e["is_change"] for e in entries] == [True, False, False]


async def test_anchor_history_missing_instance_404(
    client: AsyncClient,
) -> None:
    r = await client.get(
        "/api/backups/instance/9999/anchor-history?anchor=field-system-hostname"
    )
    assert r.status_code == 404


async def test_anchor_history_encrypted_audits_once(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
) -> None:
    """Walking an instance with three encrypted backups produces ONE
    ``view_decrypted`` audit entry for the whole blame drill-in,
    regardless of how many backups are touched."""
    _, session_factory, crypto = app_and_session
    inst = await _seed_instance(session_factory)

    backup_password = "unit-test-anchor-history-key"
    t0 = datetime(2026, 4, 1, tzinfo=UTC)
    for i, hostname in enumerate(["gw-a", "gw-b", "gw-c"]):
        p = tmp_path / f"daily_enc_{i}.xml"
        p.write_bytes(encrypt_pfsense_backup(_xml(hostname), backup_password))
        async with session_factory() as s:
            row = Backup(
                instance_id=inst.id,
                started_at=t0 + timedelta(days=i),
                finished_at=t0 + timedelta(days=i),
                duration_seconds=1.0,
                filename=p.name,
                path=str(p),
                size_bytes=p.stat().st_size,
                compressed=False,
                success=True,
                encrypted=True,
                encrypt_password_ct=crypto.encrypt(backup_password),
            )
            s.add(row)
            await s.commit()

    r = await client.get(
        f"/api/backups/instance/{inst.id}/anchor-history"
        "?anchor=field-system-hostname"
    )
    assert r.status_code == 200, r.text
    assert [e["value"] for e in r.json()["entries"]] == ["gw-a", "gw-b", "gw-c"]

    # Exactly one audit entry even though three backups were decrypted.
    count = await count_audit_entries(
        session_factory, "view_decrypted", "anchor_history"
    )
    assert count == 1


async def test_anchor_history_empty_instance_returns_empty_list(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
) -> None:
    """An instance with no successful backups returns an empty
    ``entries`` list (no error, no audit)."""
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)

    r = await client.get(
        f"/api/backups/instance/{inst.id}/anchor-history"
        "?anchor=field-system-hostname"
    )
    assert r.status_code == 200
    assert r.json()["entries"] == []


async def test_anchor_history_missing_password_returns_409(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
) -> None:
    """An encrypted backup row without a per-row password ciphertext
    raises ``_WalkAbortError`` inside the parse loop; the outer
    coroutine must translate it to a proper 409 HTTP response rather
    than surfacing an uncaught exception as 500. Regression guard for
    the v0.32.0 layering fix — the translation path lives inside
    ``asyncio.to_thread`` and is easy to regress invisibly."""
    _, session_factory, crypto = app_and_session
    inst = await _seed_instance(session_factory)

    # Build an encrypted file on disk but LEAVE ``encrypt_password_ct``
    # unset — mimics a row imported from an old instance before per-
    # row passwords existed.
    payload = encrypt_pfsense_backup(_xml("gw-locked"), "the-real-password")
    p = tmp_path / "daily_orphan.xml"
    p.write_bytes(payload)
    async with session_factory() as s:
        row = Backup(
            instance_id=inst.id,
            started_at=datetime(2026, 4, 1, tzinfo=UTC),
            finished_at=datetime(2026, 4, 1, tzinfo=UTC),
            duration_seconds=1.0,
            filename=p.name,
            path=str(p),
            size_bytes=p.stat().st_size,
            compressed=False,
            success=True,
            encrypted=True,
            encrypt_password_ct=None,  # the load-bearing None
        )
        s.add(row)
        await s.commit()

    r = await client.get(
        f"/api/backups/instance/{inst.id}/anchor-history"
        "?anchor=field-system-hostname"
    )
    assert r.status_code == 409, r.text
    assert "no per-row password" in r.json()["detail"]


async def test_anchor_history_malformed_xml_returns_422(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
) -> None:
    """A truncated / malformed XML file in the walk path must produce
    a 422 rather than crashing as a 500. The ``PfSenseParseError`` ->
    ``_WalkAbortError(422)`` translation is all that separates a
    crafted-input 500 from a polite client-visible rejection."""
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)

    p = tmp_path / "daily_truncated.xml"
    p.write_bytes(b"<pfsense><system><hostname>trunc")
    async with session_factory() as s:
        row = Backup(
            instance_id=inst.id,
            started_at=datetime(2026, 4, 1, tzinfo=UTC),
            finished_at=datetime(2026, 4, 1, tzinfo=UTC),
            duration_seconds=1.0,
            filename=p.name,
            path=str(p),
            size_bytes=p.stat().st_size,
            compressed=False,
            success=True,
            encrypted=False,
        )
        s.add(row)
        await s.commit()

    r = await client.get(
        f"/api/backups/instance/{inst.id}/anchor-history"
        "?anchor=field-system-hostname"
    )
    assert r.status_code == 422, r.text
    assert "could not be parsed" in r.json()["detail"]


async def test_anchor_history_mixed_encryption_audits_once(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
) -> None:
    """An instance that was unencrypted then turned encryption on has
    a mix of plain + encrypted backups. ``any_encrypted = any(...)``
    should still fire the audit exactly once and the walk should
    correctly read both shapes."""
    _, session_factory, crypto = app_and_session
    inst = await _seed_instance(session_factory)

    backup_password = "unit-test-mixed"
    t0 = datetime(2026, 4, 1, tzinfo=UTC)
    # Two plain backups, then two encrypted.
    for i, hostname in enumerate(["gw-a", "gw-b"]):
        p = tmp_path / f"plain_{i}.xml"
        p.write_bytes(_xml(hostname))
        async with session_factory() as s:
            s.add(Backup(
                instance_id=inst.id,
                started_at=t0 + timedelta(days=i),
                finished_at=t0 + timedelta(days=i),
                duration_seconds=1.0,
                filename=p.name,
                path=str(p),
                size_bytes=p.stat().st_size,
                compressed=False,
                success=True,
                encrypted=False,
            ))
            await s.commit()
    for i, hostname in enumerate(["gw-c", "gw-d"], start=2):
        p = tmp_path / f"enc_{i}.xml"
        p.write_bytes(encrypt_pfsense_backup(_xml(hostname), backup_password))
        async with session_factory() as s:
            s.add(Backup(
                instance_id=inst.id,
                started_at=t0 + timedelta(days=i),
                finished_at=t0 + timedelta(days=i),
                duration_seconds=1.0,
                filename=p.name,
                path=str(p),
                size_bytes=p.stat().st_size,
                compressed=False,
                success=True,
                encrypted=True,
                encrypt_password_ct=crypto.encrypt(backup_password),
            ))
            await s.commit()

    r = await client.get(
        f"/api/backups/instance/{inst.id}/anchor-history"
        "?anchor=field-system-hostname"
    )
    assert r.status_code == 200, r.text
    values = [e["value"] for e in r.json()["entries"]]
    assert values == ["gw-a", "gw-b", "gw-c", "gw-d"]

    # Single audit entry even though only SOME of the backups were
    # encrypted — the audit signals the drill-in as a whole.
    count = await count_audit_entries(
        session_factory, "view_decrypted", "anchor_history"
    )
    assert count == 1
