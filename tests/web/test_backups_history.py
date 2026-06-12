"""Tests for the v0.45.0 ``GET /api/backups/history`` scrubber feed.

Covers:

- Empty + single-row cases.
- Server-side ``success = true`` filter (failed rows are not returned).
- Server-side instance scoping (other instances' rows are not returned).
- ASC ordering by ``started_at``.
- ``instance_id`` is required (422 when missing).
- Lean schema shape: only the 5 fields the scrubber renders.
- No cap: returns the full set even for very large histories.
- ``changes_since_first`` LEFT JOIN populates from ``backup_diff`` rows
  with ``kind == "first"`` and renders ``null`` for backups without
  such a row.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pfsense_shared.crypto import Crypto
from pfsense_shared.models import Backup, BackupDiff

from .conftest import _seed_instance


async def _seed_one(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    instance_id: int,
    started_at: datetime,
    success: bool = True,
    tag: str | None = None,
    size_bytes: int = 1024,
    config_version: str | None = None,
) -> int:
    async with session_factory() as s:
        row = Backup(
            instance_id=instance_id,
            started_at=started_at,
            finished_at=started_at,
            duration_seconds=1.0,
            filename=f"daily_{started_at.isoformat()}.xml",
            path=f"/tmp/daily_{started_at.isoformat()}.xml",
            size_bytes=size_bytes,
            compressed=False,
            success=success,
            encrypted=False,
            tag=tag,
            config_version=config_version,
        )
        s.add(row)
        await s.commit()
        await s.refresh(row)
        return row.id


async def test_history_requires_instance_id(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
) -> None:
    """``instance_id`` is required — the scrubber is per-instance by
    design, and a global "history" doesn't make semantic sense."""
    r = await client.get("/api/backups/history")
    assert r.status_code == 422


async def test_history_empty_returns_empty_array(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
) -> None:
    """No backups → ``[]``. The scrubber UI renders its empty state."""
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)
    r = await client.get(f"/api/backups/history?instance_id={inst.id}")
    assert r.status_code == 200
    assert r.json() == []


async def test_history_filters_failed_rows_server_side(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
) -> None:
    """Pre-v0.45.0 the frontend filtered ``success === true`` after
    fetching; the new endpoint applies the filter server-side so
    failed rows never hit the wire."""
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)
    t0 = datetime(2026, 4, 1, tzinfo=UTC)

    ok_a = await _seed_one(session_factory, instance_id=inst.id, started_at=t0)
    await _seed_one(
        session_factory,
        instance_id=inst.id,
        started_at=t0 + timedelta(hours=1),
        success=False,
    )
    ok_b = await _seed_one(
        session_factory,
        instance_id=inst.id,
        started_at=t0 + timedelta(hours=2),
    )

    r = await client.get(f"/api/backups/history?instance_id={inst.id}")
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()]
    assert ids == [ok_a, ok_b]


async def test_history_orders_asc_by_started_at(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
) -> None:
    """Scrubber needs ascending order so array indexes map onto a
    left-to-right timeline. Insertion order isn't necessarily ASC, so
    seed deliberately out-of-order and verify the response shape."""
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)
    t0 = datetime(2026, 4, 1, tzinfo=UTC)

    # Seed t+2, then t+0, then t+1 — server must sort.
    mid = await _seed_one(
        session_factory, instance_id=inst.id, started_at=t0 + timedelta(hours=2)
    )
    first = await _seed_one(session_factory, instance_id=inst.id, started_at=t0)
    second = await _seed_one(
        session_factory, instance_id=inst.id, started_at=t0 + timedelta(hours=1)
    )

    r = await client.get(f"/api/backups/history?instance_id={inst.id}")
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()]
    assert ids == [first, second, mid]


async def test_history_scopes_to_instance(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
) -> None:
    """A backup belonging to another instance must not appear in the
    requested instance's history feed."""
    _, session_factory, _ = app_and_session
    inst_a = await _seed_instance(session_factory)
    async with session_factory() as s:
        # Second instance — reuse the seed helper would clobber the
        # name unique index, so build a distinct one inline.
        from pfsense_shared.models import Instance

        inst_b = Instance(
            name="gw-other",
            url="https://other.test",
            username_ct=b"x",
            password_ct=b"x",
            subfolder=None,
            backup_prefix="daily",
            verify_ssl=False,
            timeout_seconds=30,
            enabled=True,
            retention_count=10,
        )
        s.add(inst_b)
        await s.commit()
        await s.refresh(inst_b)

    t0 = datetime(2026, 4, 1, tzinfo=UTC)
    a_id = await _seed_one(session_factory, instance_id=inst_a.id, started_at=t0)
    await _seed_one(session_factory, instance_id=inst_b.id, started_at=t0)

    r = await client.get(f"/api/backups/history?instance_id={inst_a.id}")
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()]
    assert ids == [a_id]


async def test_history_row_has_lean_schema(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
) -> None:
    """Each row carries exactly the 6 fields the scrubber renders. The
    wide BackupListItem columns (filename, area, encrypted, …) are
    NOT included — keeping the payload small was the whole point."""
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)
    t0 = datetime(2026, 4, 1, tzinfo=UTC)
    await _seed_one(
        session_factory,
        instance_id=inst.id,
        started_at=t0,
        tag="pre-upgrade",
        size_bytes=2048,
    )

    r = await client.get(f"/api/backups/history?instance_id={inst.id}")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    row = rows[0]
    assert set(row.keys()) == {
        "id",
        "started_at",
        "size_bytes",
        "tag",
        "changes_since_first",
        "config_version",
    }
    assert row["tag"] == "pre-upgrade"
    assert row["size_bytes"] == 2048
    assert row["changes_since_first"] is None
    # Specifically: the wide fields are gone.
    for absent in (
        "filename",
        "instance_id",
        "instance_name",
        "duration_seconds",
        "area",
        "encrypted",
        "compressed",
        "note",
        "included_rrd",
        "included_packages",
        "included_ssh",
        "success",  # filtered out server-side, no need to ship the flag
    ):
        assert absent not in row, f"{absent!r} should not appear in lean schema"


async def test_history_changes_since_first_left_join(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
) -> None:
    """A ``backup_diff`` row with ``kind == 'first'`` populates
    ``changes_since_first`` on the matching backup; backups without
    such a row come back as ``null``."""
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)
    t0 = datetime(2026, 4, 1, tzinfo=UTC)

    base = await _seed_one(session_factory, instance_id=inst.id, started_at=t0)
    later = await _seed_one(
        session_factory,
        instance_id=inst.id,
        started_at=t0 + timedelta(days=1),
    )

    # Hand-craft a precomputed diff row for ``later``. Compute path
    # is exercised separately by ``test_backup_diff.py``; here we
    # only care that the LEFT JOIN surfaces the counts.
    async with session_factory() as s:
        s.add(
            BackupDiff(
                backup_id=later,
                kind="first",
                base_backup_id=base,
                added_count=3,
                removed_count=1,
                modified_count=7,
                # ``full_diff_gz`` is NOT NULL in the schema; the
                # JOIN that powers this test only reads count
                # columns, so an empty blob is fine.
                full_diff_gz=b"",
            )
        )
        await s.commit()

    r = await client.get(f"/api/backups/history?instance_id={inst.id}")
    assert r.status_code == 200
    rows = {row["id"]: row for row in r.json()}
    assert rows[base]["changes_since_first"] is None
    assert rows[later]["changes_since_first"] == {
        "added": 3,
        "removed": 1,
        "modified": 7,
    }


async def test_history_returns_more_than_100_rows(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
) -> None:
    """The whole point of v0.45.0 — no 100-row cap. Seed 250 rows
    and assert all of them come back."""
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)
    t0 = datetime(2026, 4, 1, tzinfo=UTC)

    # Bulk-insert in a single session to keep the test cheap.
    async with session_factory() as s:
        for i in range(250):
            s.add(
                Backup(
                    instance_id=inst.id,
                    started_at=t0 + timedelta(hours=i),
                    finished_at=t0 + timedelta(hours=i),
                    duration_seconds=1.0,
                    filename=f"daily_{i:04d}.xml",
                    path=f"/tmp/daily_{i:04d}.xml",
                    size_bytes=512,
                    compressed=False,
                    success=True,
                    encrypted=False,
                )
            )
        await s.commit()

    r = await client.get(f"/api/backups/history?instance_id={inst.id}")
    assert r.status_code == 200
    assert len(r.json()) == 250


async def test_history_surfaces_config_version(
    client, app_and_session
) -> None:
    """F5: ``config_version`` rides the scrubber feed (NULL-safe)."""
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)
    t0 = datetime(2026, 6, 1, tzinfo=UTC)
    await _seed_one(
        session_factory, instance_id=inst.id, started_at=t0, config_version="23.3"
    )
    await _seed_one(
        session_factory,
        instance_id=inst.id,
        started_at=t0 + timedelta(days=1),
        config_version=None,
    )

    r = await client.get(f"/api/backups/history?instance_id={inst.id}")
    assert r.status_code == 200
    body = r.json()
    assert [row["config_version"] for row in body] == ["23.3", None]
