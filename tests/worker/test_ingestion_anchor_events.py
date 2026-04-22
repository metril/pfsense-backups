"""End-to-end ingestion test for the AnchorEvent write path.

Drives ``PfSenseBackupManager._compute_and_persist_diffs`` directly
over a fake filesystem + in-memory SQLite. Three synthetic backups:

- Backup 1 seeds events (first-ever → one event per anchor present,
  kind=added, prev_backup_id NULL, instance marked backfilled).
- Backup 2 diffs against #1 (adds an alias + changes the hostname —
  expect an ``added`` event for the new alias and a ``modified``
  event for ``field-system-hostname``).
- Backup 3 diffs against #2 (deletes the alias — expect a
  ``removed`` event).

The ``_compute_and_persist_diffs`` path also writes ``BackupDiff``
rows; we keep asserting on that too to guard against regression on
the combined write transaction.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pfsense_shared.crypto import Crypto
from pfsense_shared.models import (
    AnchorEvent,
    Backup,
    BackupDiff,
    Base,
    Instance,
)
from worker.backup_manager import PfSenseBackupManager

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


def _seed_backup(
    session_factory,
    backup_dir: Path,
    instance_id: int,
    when: datetime,
    hostname: str,
    aliases: list[str],
) -> int:
    p = backup_dir / f"daily_{when.isoformat().replace(':', '-')}.xml"
    p.write_bytes(_xml(hostname, aliases))
    with session_factory() as s:
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
        s.commit()
        s.refresh(row)
        return row.id


def _make_manager(session_factory, crypto: Crypto) -> PfSenseBackupManager:
    # The manager takes several collaborators that _compute_and_persist_diffs
    # doesn't touch; MagicMock is a cheap stand-in so we don't wire up the
    # real IPC + metrics + notifier stack for a DB-only test.
    return PfSenseBackupManager(
        session_factory=session_factory,
        publisher=MagicMock(),
        metrics=MagicMock(),
        crypto=crypto,
        notifier=MagicMock(),
        hostname="test-host",
        instance_locks=MagicMock(),
        cross_process_lock=MagicMock(),
    )


def test_ingestion_emits_seed_diff_remove(tmp_path: Path) -> None:
    # In-memory SQLite + a sync session factory (what the worker uses).
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)

    crypto = Crypto(Fernet.generate_key())

    # Seed an instance.
    with session_factory() as s:
        inst = Instance(
            name="gw-test",
            url="https://gw.test",
            username_ct=crypto.encrypt("admin"),
            password_ct=crypto.encrypt("hunter2"),
            subfolder=None,
            backup_prefix="daily",
        )
        s.add(inst)
        s.commit()
        s.refresh(inst)
        instance_id = inst.id

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    t0 = datetime(2026, 4, 1, tzinfo=UTC)

    # Backup 1 — first-ever. Seed pass fires.
    b1 = _seed_backup(
        session_factory, backup_dir, instance_id, t0, "gw-a", ["RFC1918"]
    )
    manager = _make_manager(session_factory, crypto)
    manager._compute_and_persist_diffs(b1, instance_id)

    with session_factory() as s:
        events = s.execute(
            select(AnchorEvent).where(AnchorEvent.backup_id == b1)
        ).scalars().all()
        # Expect: one hostname field event + one alias row event (at
        # minimum — more singleton fields may emit, but the core
        # anchors must be present).
        ids = {e.anchor_id for e in events}
        assert "field-system-hostname" in ids
        assert "xref-alias-RFC1918" in ids
        # All seed events have kind=added and prev_backup_id=None.
        for e in events:
            assert e.kind == "added"
            assert e.prev_backup_id is None

        inst = s.get(Instance, instance_id)
        assert inst is not None
        assert inst.anchor_events_backfilled_at is not None

    # Backup 2 — hostname change + new alias.
    b2 = _seed_backup(
        session_factory,
        backup_dir,
        instance_id,
        t0 + timedelta(days=1),
        "gw-b",
        ["RFC1918", "BOGON"],
    )
    manager._compute_and_persist_diffs(b2, instance_id)

    with session_factory() as s:
        b2_events = s.execute(
            select(AnchorEvent).where(AnchorEvent.backup_id == b2)
        ).scalars().all()
        by_id = {(e.anchor_id, e.kind) for e in b2_events}
        assert ("field-system-hostname", "modified") in by_id
        assert ("xref-alias-BOGON", "added") in by_id
        # All b2 events point back at b1.
        for e in b2_events:
            assert e.prev_backup_id == b1

        # BackupDiff rows landed alongside (sanity that the
        # refactor didn't break the existing path).
        diff_rows = s.execute(
            select(BackupDiff).where(BackupDiff.backup_id == b2)
        ).all()
        kinds = {r[0].kind for r in diff_rows}
        assert kinds == {"previous", "first"}

    # Backup 3 — alias removed, hostname unchanged.
    b3 = _seed_backup(
        session_factory,
        backup_dir,
        instance_id,
        t0 + timedelta(days=2),
        "gw-b",
        ["RFC1918"],
    )
    manager._compute_and_persist_diffs(b3, instance_id)

    with session_factory() as s:
        b3_events = s.execute(
            select(AnchorEvent).where(AnchorEvent.backup_id == b3)
        ).scalars().all()
        kinds_by_id = {(e.anchor_id, e.kind) for e in b3_events}
        assert ("xref-alias-BOGON", "removed") in kinds_by_id
        # No hostname event — nothing changed.
        hostname_events = [e for e in b3_events if e.anchor_id == "field-system-hostname"]
        assert hostname_events == []
