"""Integration tests for the v0.37.0 ``backup_diff`` pipeline.

Covers:

- ``/api/backups/{id}/diff-summary`` populates + caches rows on first
  read (the lazy-backfill path for backups that predate v0.37.0).
- The per-instance history endpoint's LEFT JOIN against
  ``backup_diff`` surfaces ``changes_since_first`` in
  ``/api/backups/history`` responses once a diff row exists.
  (v0.45.0: moved off the wide list endpoint to the lean history
  endpoint — the global list never rendered the field anyway.)
- ``/api/backups/{id}/diff-vs-first/parsed`` returns the full
  ``ConfigDiff`` payload, served from the cached ``full_diff_gz``
  blob on second access.
- Staleness detection: when the first backup is deleted, the next
  summary request recomputes against the new first, updating
  ``base_backup_id``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pfsense_shared.crypto import Crypto
from pfsense_shared.models import Backup, BackupDiff

from .conftest import _seed_instance

_BASE_XML = """<?xml version="1.0"?>
<pfsense>
  <version>21.9</version>
  <system>
    <hostname>{hostname}</hostname>
    <domain>lan.example</domain>
    <timezone>UTC</timezone>
  </system>
  <aliases>
{alias_xml}  </aliases>
</pfsense>
"""


def _xml(hostname: str, alias_names: list[str]) -> bytes:
    aliases = "".join(
        f"    <alias><name>{n}</name><type>host</type>"
        f"<address>192.0.2.{i + 1}</address></alias>\n"
        for i, n in enumerate(alias_names)
    )
    return _BASE_XML.format(hostname=hostname, alias_xml=aliases).encode()


async def _seed_backup(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    instance_id: int,
    when: datetime,
    hostname: str,
    aliases: list[str],
) -> int:
    p = tmp_path / f"daily_{when.isoformat()}_{hostname}.xml"
    p.write_bytes(_xml(hostname, aliases))
    async with session_factory() as s:
        row = Backup(
            instance_id=instance_id,
            started_at=when,
            finished_at=when,
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
        await s.refresh(row)
        return row.id


async def test_diff_summary_populates_and_caches(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
) -> None:
    """First read of ``/diff-summary`` computes both diffs and
    persists them. Second read hits the cached rows — observable by
    the row count in ``backup_diff`` growing once, then holding."""
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)

    t0 = datetime(2026, 4, 1, tzinfo=UTC)
    first_id = await _seed_backup(
        session_factory, tmp_path, inst.id, t0, "gw-a", ["a1"]
    )
    second_id = await _seed_backup(
        session_factory,
        tmp_path,
        inst.id,
        t0 + timedelta(days=1),
        "gw-b",
        ["a1", "a2"],
    )

    r = await client.get(f"/api/backups/{second_id}/diff-summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["vs_previous"] is not None
    assert body["vs_first"] is not None
    assert body["first_backup_id"] == first_id
    # The diff between t0 and t0+1 adds one alias + changes the hostname.
    assert body["vs_first"]["added"] == 1
    assert body["vs_first"]["modified"] >= 1  # hostname modified

    # Second call should NOT insert additional rows.
    async with session_factory() as s:
        pre = (
            await s.execute(select(BackupDiff).where(BackupDiff.backup_id == second_id))
        ).all()
    r2 = await client.get(f"/api/backups/{second_id}/diff-summary")
    assert r2.status_code == 200
    async with session_factory() as s:
        post = (
            await s.execute(select(BackupDiff).where(BackupDiff.backup_id == second_id))
        ).all()
    assert len(pre) == len(post) == 2  # 'previous' + 'first'


async def test_backup_history_surfaces_changes_since_first(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
) -> None:
    """Once a diff row exists, ``/api/backups/history?instance_id=…``
    returns ``changes_since_first`` for that backup via LEFT JOIN.
    Other rows (no diff yet) render ``null``.

    v0.45.0: the JOIN moved from ``/api/backups`` to the dedicated
    ``/api/backups/history`` scrubber endpoint.
    """
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)

    t0 = datetime(2026, 4, 1, tzinfo=UTC)
    first_id = await _seed_backup(
        session_factory, tmp_path, inst.id, t0, "gw-a", ["a1"]
    )
    second_id = await _seed_backup(
        session_factory,
        tmp_path,
        inst.id,
        t0 + timedelta(days=1),
        "gw-b",
        ["a1", "a2"],
    )
    # Trigger diff population for the second backup only.
    await client.get(f"/api/backups/{second_id}/diff-summary")

    r = await client.get(f"/api/backups/history?instance_id={inst.id}")
    assert r.status_code == 200
    rows = {row["id"]: row for row in r.json()}
    # First backup was diffed against NO earlier backup → no row →
    # changes_since_first is null.
    assert rows[first_id]["changes_since_first"] is None
    assert rows[second_id]["changes_since_first"] is not None
    assert rows[second_id]["changes_since_first"]["added"] == 1


async def test_diff_vs_first_parsed_returns_full_configdiff(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
) -> None:
    """``/diff-vs-first/parsed`` serves the cached ``full_diff_gz``
    payload, ungzipped back to the ``ConfigDiff`` JSON shape the
    frontend's ``ParsedBackupDiff`` component expects. Key shape
    assertions: top-level section keys exist, aliases section
    reports the added entry."""
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)
    t0 = datetime(2026, 4, 1, tzinfo=UTC)
    await _seed_backup(session_factory, tmp_path, inst.id, t0, "gw-a", ["a1"])
    second_id = await _seed_backup(
        session_factory,
        tmp_path,
        inst.id,
        t0 + timedelta(days=1),
        "gw-b",
        ["a1", "a2"],
    )

    r = await client.get(f"/api/backups/{second_id}/diff-vs-first/parsed")
    assert r.status_code == 200, r.text
    body = r.json()
    # Full ConfigDiff — structural diff is present.
    assert "aliases" in body
    assert "system" in body
    # Aliases: one added entry (a2).
    added_names = [a.get("name") for a in body["aliases"]["added"]]
    assert "a2" in added_names


async def test_diff_vs_first_404_on_single_backup(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
) -> None:
    """When an instance has only one successful backup, there's no
    'first other' to diff against — endpoint 404s with a message."""
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)
    t0 = datetime(2026, 4, 1, tzinfo=UTC)
    only_id = await _seed_backup(
        session_factory, tmp_path, inst.id, t0, "gw-a", ["a1"]
    )
    r = await client.get(f"/api/backups/{only_id}/diff-vs-first/parsed")
    assert r.status_code == 404


async def test_staleness_recompute_when_first_deleted(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
) -> None:
    """When the baseline backup is pruned, ``base_backup_id`` goes
    NULL (ON DELETE SET NULL). Next read detects the mismatch and
    recomputes against the new first, upserting with a fresh base."""
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)
    t0 = datetime(2026, 4, 1, tzinfo=UTC)
    first_id = await _seed_backup(
        session_factory, tmp_path, inst.id, t0, "gw-a", ["a1"]
    )
    middle_id = await _seed_backup(
        session_factory,
        tmp_path,
        inst.id,
        t0 + timedelta(days=1),
        "gw-b",
        ["a1"],
    )
    third_id = await _seed_backup(
        session_factory,
        tmp_path,
        inst.id,
        t0 + timedelta(days=2),
        "gw-c",
        ["a1"],
    )

    # Populate diff rows for the third backup (base_backup_id will
    # initially point at first_id).
    r = await client.get(f"/api/backups/{third_id}/diff-summary")
    assert r.status_code == 200
    assert r.json()["first_backup_id"] == first_id

    # Delete the first backup (retention path). CASCADE + SET NULL
    # on the FK kicks in.
    async with session_factory() as s:
        first = await s.get(Backup, first_id)
        await s.delete(first)
        await s.commit()

    # Next summary call — the read path detects base mismatch and
    # recomputes against the new first (middle_id).
    r2 = await client.get(f"/api/backups/{third_id}/diff-summary")
    assert r2.status_code == 200
    assert r2.json()["first_backup_id"] == middle_id

    async with session_factory() as s:
        row = await s.get(BackupDiff, (third_id, "first"))
        assert row is not None
        assert row.base_backup_id == middle_id
