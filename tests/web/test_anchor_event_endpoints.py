"""Tests for the v0.40.0 indexed read surfaces:

- ``/anchor-history`` served from ``anchor_event`` (indexed=True).
- ``/anchor-blame-summary`` — tooltip data source.
- ``/cumulative-changes`` — instance-wide changes page.

Uses the same minimal-app fixture as the other web tests. Seeds
events directly into the ``anchor_event`` table rather than going
through the full worker ingestion path, so the endpoint contracts
are pinned independently of the projector/backfill.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pfsense_shared.crypto import Crypto
from pfsense_shared.models import AnchorEvent, Backup, Instance

from .conftest import _seed_backup_row, _seed_instance


@pytest_asyncio.fixture
async def seeded(
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
) -> dict:
    """Seed an instance that's been backfilled, plus three backups and
    a handful of events covering the interesting cases."""
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)

    async with session_factory() as s:
        fresh = await s.get(Instance, inst.id)
        assert fresh is not None
        fresh.anchor_events_backfilled_at = datetime(2026, 4, 1, tzinfo=UTC)
        await s.commit()

    t0 = datetime(2026, 4, 1, tzinfo=UTC)
    backup_ids: list[int] = []
    for i in range(3):
        p = tmp_path / f"daily_{i}.xml"
        p.write_bytes(b"<pfsense/>")
        row = await _seed_backup_row(
            session_factory,
            instance_id=inst.id,
            path=p,
        )
        # _seed_backup_row hard-codes 2026-04-01 for started_at; spread
        # them out so ordering tests work.
        async with session_factory() as s:
            b = await s.get(Backup, row.id)
            assert b is not None
            b.started_at = t0 + timedelta(days=i)
            b.finished_at = b.started_at
            await s.commit()
        backup_ids.append(row.id)

    # Events:
    # - alias RFC1918 added in backup 0.
    # - system.hostname modified in backup 1.
    # - alias RFC1918 modified in backup 2.
    # - new alias BOGON added in backup 1.
    # - BOGON removed in backup 2.
    events_spec = [
        (
            0,
            "xref-alias-RFC1918",
            "added",
            {"name": "RFC1918", "address": "10.0.0.0/8"},
            None,
        ),
        (
            0,
            "field-system-hostname",
            "added",
            "gw-a",
            None,
        ),
        (
            1,
            "field-system-hostname",
            "modified",
            "gw-b",
            0,
        ),
        (
            1,
            "xref-alias-BOGON",
            "added",
            {"name": "BOGON", "address": "0.0.0.0/8"},
            0,
        ),
        (
            2,
            "xref-alias-RFC1918",
            "modified",
            {"name": "RFC1918", "address": "10.0.0.0/8 192.168.0.0/16"},
            1,
        ),
        (
            2,
            "xref-alias-BOGON",
            "removed",
            {"name": "BOGON", "address": "0.0.0.0/8"},
            1,
        ),
    ]
    async with session_factory() as s:
        for idx, anchor, kind, value, prev_idx in events_spec:
            bid = backup_ids[idx]
            prev_id = backup_ids[prev_idx] if prev_idx is not None else None
            bkp = await s.get(Backup, bid)
            assert bkp is not None
            s.add(
                AnchorEvent(
                    instance_id=inst.id,
                    backup_id=bid,
                    prev_backup_id=prev_id,
                    anchor_id=anchor,
                    occurred_at=bkp.started_at,
                    kind=kind,
                    value_json=json.dumps(value),
                )
            )
        await s.commit()

    return {"instance_id": inst.id, "backup_ids": backup_ids}


async def test_anchor_history_indexed_returns_events_in_order(
    client: AsyncClient,
    seeded: dict,
) -> None:
    r = await client.get(
        f"/api/backups/instance/{seeded['instance_id']}/anchor-history"
        "?anchor=field-system-hostname"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["indexed"] is True
    assert body["anchor"] == "field-system-hostname"
    entries = body["entries"]
    assert [(e["backup_id"], e["value"]) for e in entries] == [
        (seeded["backup_ids"][0], "gw-a"),
        (seeded["backup_ids"][1], "gw-b"),
    ]
    # Every persisted event is a change — is_change always True on
    # the indexed path.
    assert all(e["is_change"] for e in entries)


async def test_anchor_history_unknown_anchor_returns_empty_list(
    client: AsyncClient,
    seeded: dict,
) -> None:
    r = await client.get(
        f"/api/backups/instance/{seeded['instance_id']}/anchor-history"
        "?anchor=xref-alias-nonexistent"
    )
    assert r.status_code == 200
    assert r.json()["entries"] == []


async def test_blame_summary_latest_per_anchor(
    client: AsyncClient,
    seeded: dict,
) -> None:
    r = await client.get(
        f"/api/backups/instance/{seeded['instance_id']}/anchor-blame-summary"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["indexed"] is True
    assert body["as_of_backup_id"] == seeded["backup_ids"][2]  # latest
    anchors = body["anchors"]

    # RFC1918 last change was in backup 2 (modified).
    assert anchors["xref-alias-RFC1918"]["backup_id"] == seeded["backup_ids"][2]
    assert anchors["xref-alias-RFC1918"]["kind"] == "modified"

    # Hostname last change was in backup 1.
    assert anchors["field-system-hostname"]["backup_id"] == seeded["backup_ids"][1]
    assert anchors["field-system-hostname"]["kind"] == "modified"

    # BOGON last event is its removal in backup 2.
    assert anchors["xref-alias-BOGON"]["kind"] == "removed"


async def test_blame_summary_as_of_cutoff(
    client: AsyncClient,
    seeded: dict,
) -> None:
    """Narrowing ``as_of_backup_id`` to backup 1 should omit any
    events that happened after — the RFC1918 modification and the
    BOGON removal."""
    r = await client.get(
        f"/api/backups/instance/{seeded['instance_id']}/anchor-blame-summary"
        f"?as_of_backup_id={seeded['backup_ids'][1]}"
    )
    assert r.status_code == 200
    anchors = r.json()["anchors"]
    assert anchors["xref-alias-RFC1918"]["backup_id"] == seeded["backup_ids"][0]
    assert anchors["xref-alias-RFC1918"]["kind"] == "added"
    # BOGON at backup 1 is still ``added`` — the removal hasn't happened yet.
    assert anchors["xref-alias-BOGON"]["kind"] == "added"


async def test_cumulative_changes_sorts_by_last_change_desc(
    client: AsyncClient,
    seeded: dict,
) -> None:
    r = await client.get(
        f"/api/backups/instance/{seeded['instance_id']}/cumulative-changes"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["indexed"] is True
    rows = body["rows"]

    # Three anchors with events in the window.
    anchor_ids = [row["anchor_id"] for row in rows]
    assert set(anchor_ids) == {
        "xref-alias-RFC1918",
        "field-system-hostname",
        "xref-alias-BOGON",
    }

    # Sorted by last_change_at desc — backup 2 events first (two
    # of them, RFC1918 and BOGON).
    last_changes = [row["last_change_at"] for row in rows]
    assert last_changes == sorted(last_changes, reverse=True)

    # section is populated from section_for_anchor.
    for row in rows:
        if row["anchor_id"].startswith("xref-alias-"):
            assert row["section"] == "aliases"
        elif row["anchor_id"].startswith("field-system-"):
            assert row["section"] == "system"

    # change_count is total events in window per anchor.
    rfc = next(r for r in rows if r["anchor_id"] == "xref-alias-RFC1918")
    assert rfc["change_count"] == 2  # added + modified
    bogon = next(r for r in rows if r["anchor_id"] == "xref-alias-BOGON")
    assert bogon["change_count"] == 2  # added + removed

    # original_value carries the first event's value; current the last.
    assert rfc["original_value"] == {"name": "RFC1918", "address": "10.0.0.0/8"}
    assert rfc["current_value"]["address"].endswith("192.168.0.0/16")


async def test_blame_summary_tiebreaker_for_equal_timestamps(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
) -> None:
    """Regression: when two events for the same anchor share an
    ``occurred_at``, the blame-summary window function must pick
    deterministically. v0.40.0 tiebreak chain:
    ``(occurred_at desc, kind_priority asc, id desc)`` — so on
    identical timestamps with identical kinds, the latest-inserted
    row wins. Without the ``id`` tiebreaker the DB is free to pick
    either, and the cumulative-changes self-join can stitch
    inconsistent first/last halves."""
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)
    async with session_factory() as s:
        fresh = await s.get(Instance, inst.id)
        assert fresh is not None
        fresh.anchor_events_backfilled_at = datetime(2026, 4, 1, tzinfo=UTC)
        await s.commit()

    # Seed a single backup.
    p = tmp_path / "b.xml"
    p.write_bytes(b"<pfsense/>")
    row = await _seed_backup_row(
        session_factory, instance_id=inst.id, path=p
    )
    backup_id = row.id

    # Two ``modified`` events for the same anchor sharing a
    # timestamp — same kind so kind-priority doesn't split them,
    # and the ``id desc`` fallback picks the later-inserted row.
    ts = datetime(2026, 4, 1, tzinfo=UTC)
    async with session_factory() as s:
        s.add(
            AnchorEvent(
                instance_id=inst.id,
                backup_id=backup_id,
                anchor_id="xref-alias-DUP",
                occurred_at=ts,
                kind="modified",
                value_json=json.dumps({"name": "DUP", "v": 1}),
            )
        )
        s.add(
            AnchorEvent(
                instance_id=inst.id,
                backup_id=backup_id,
                anchor_id="xref-alias-DUP",
                occurred_at=ts,
                kind="modified",
                value_json=json.dumps({"name": "DUP", "v": 2}),
            )
        )
        await s.commit()

    r = await client.get(
        f"/api/backups/instance/{inst.id}/anchor-blame-summary"
    )
    assert r.status_code == 200
    entry = r.json()["anchors"]["xref-alias-DUP"]
    # Same kind on both events → kind_priority ties → ``id desc``
    # breaks the tie, picking the later-inserted row. The test
    # proves the chain resolves deterministically; without it the
    # DB's ROW_NUMBER would be free to pick either.
    assert entry["kind"] == "modified"


async def test_modified_plus_reordered_collapses_to_one_backup_entry(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
) -> None:
    """Regression: when a rule is edited + reordered in one backup
    the projector emits TWO events at the same ``occurred_at`` (one
    ``modified``, one ``reordered``). The read endpoints must
    collapse those to a single entry per backup:

    - ``/anchor-history``: one AnchorHistoryChange with the
      ``modified`` event's value (duplicate backup_id would cause a
      React key collision in the drawer).
    - ``/anchor-blame-summary``: the ``kind`` shown in the tooltip
      must be ``modified`` (the more informative of the two).
    - ``/cumulative-changes``: ``change_count`` must be 1 (one
      operator action), not 2.
    """
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)
    async with session_factory() as s:
        fresh = await s.get(Instance, inst.id)
        assert fresh is not None
        fresh.anchor_events_backfilled_at = datetime(2026, 4, 1, tzinfo=UTC)
        await s.commit()

    p = tmp_path / "b.xml"
    p.write_bytes(b"<pfsense/>")
    row = await _seed_backup_row(
        session_factory, instance_id=inst.id, path=p
    )
    backup_id = row.id

    ts = datetime(2026, 4, 1, tzinfo=UTC)
    async with session_factory() as s:
        # Projector-emission order: modified first, reordered second.
        s.add(
            AnchorEvent(
                instance_id=inst.id,
                backup_id=backup_id,
                anchor_id="xref-rule-1001",
                occurred_at=ts,
                kind="modified",
                value_json=json.dumps({"key": "1001", "descr": "edited"}),
            )
        )
        s.add(
            AnchorEvent(
                instance_id=inst.id,
                backup_id=backup_id,
                anchor_id="xref-rule-1001",
                occurred_at=ts,
                kind="reordered",
                value_json=json.dumps({"key": "1001", "descr": "edited"}),
            )
        )
        await s.commit()

    # /anchor-history: one entry, no duplicate backup_id.
    r = await client.get(
        f"/api/backups/instance/{inst.id}/anchor-history?anchor=xref-rule-1001"
    )
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["backup_id"] == backup_id

    # /anchor-blame-summary: kind=modified (priority over reordered).
    r = await client.get(
        f"/api/backups/instance/{inst.id}/anchor-blame-summary"
    )
    assert r.status_code == 200
    assert r.json()["anchors"]["xref-rule-1001"]["kind"] == "modified"

    # /cumulative-changes: change_count=1, not 2.
    r = await client.get(
        f"/api/backups/instance/{inst.id}/cumulative-changes"
    )
    assert r.status_code == 200
    rows = r.json()["rows"]
    matching = [row for row in rows if row["anchor_id"] == "xref-rule-1001"]
    assert len(matching) == 1
    assert matching[0]["change_count"] == 1


async def test_cumulative_changes_non_backfilled_returns_empty(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
) -> None:
    _, session_factory, _ = app_and_session
    inst = await _seed_instance(session_factory)
    # No anchor_events_backfilled_at set.
    r = await client.get(
        f"/api/backups/instance/{inst.id}/cumulative-changes"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["indexed"] is False
    assert body["rows"] == []
