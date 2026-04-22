"""End-to-end test for ``python -m worker reindex-anchor-events``.

Seeds three successful backups for an instance whose
``anchor_events_backfilled_at`` is NULL, drives the private
``_reindex_one_instance`` helper directly (same entry point the CLI
uses; avoids pulling in the settings + key file plumbing that
``reindex_anchor_events`` wires up), and asserts:

- Seed events exist for the oldest backup (kind=added,
  prev_backup_id=None).
- Diff-projected events exist for every pair.
- The instance's ``anchor_events_backfilled_at`` is set.
- Rerunning the reindex produces the same row count (idempotent —
  truncate-then-insert per instance).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pfsense_shared.crypto import Crypto
from pfsense_shared.models import AnchorEvent, Backup, Base, Instance
from worker.__main__ import _reindex_one_instance

_XML = """<?xml version="1.0"?>
<pfsense>
  <version>21.9</version>
  <system>
    <hostname>{hostname}</hostname>
    <domain>lan.example</domain>
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
    return _XML.format(hostname=hostname, alias_xml=aliases).encode()


def test_reindex_fills_and_is_idempotent(tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)

    crypto = Crypto(Fernet.generate_key())

    with session_factory() as s:
        inst = Instance(
            name="gw-reindex",
            url="https://gw.reindex.test",
            username_ct=crypto.encrypt("admin"),
            password_ct=crypto.encrypt("p"),
            backup_prefix="daily",
        )
        s.add(inst)
        s.commit()
        s.refresh(inst)
        instance_id = inst.id

    t0 = datetime(2026, 4, 1, tzinfo=UTC)
    backup_dir = tmp_path / "b"
    backup_dir.mkdir()
    specs = [
        (t0, "gw-a", ["RFC1918"]),
        (t0 + timedelta(days=1), "gw-b", ["RFC1918", "BOGON"]),
        (t0 + timedelta(days=2), "gw-b", ["RFC1918"]),
    ]
    backup_ids: list[int] = []
    for when, hostname, aliases in specs:
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
            backup_ids.append(row.id)

    log = logging.getLogger("test")
    first_count = _reindex_one_instance(session_factory, instance_id, crypto, log)
    assert first_count > 0

    with session_factory() as s:
        events = s.execute(
            select(AnchorEvent).where(AnchorEvent.instance_id == instance_id)
        ).scalars().all()
        assert len(events) == first_count
        # Seed events for the oldest backup.
        seed = [e for e in events if e.backup_id == backup_ids[0]]
        assert all(e.kind == "added" and e.prev_backup_id is None for e in seed)

        # Backup 2 events point at backup 1; backup 3 events point at backup 2.
        for e in events:
            if e.backup_id == backup_ids[1]:
                assert e.prev_backup_id == backup_ids[0]
            if e.backup_id == backup_ids[2]:
                assert e.prev_backup_id == backup_ids[1]

        # The alias BOGON was added in backup 2 and removed in backup 3 —
        # both should be present in the event log.
        bogon_adds = [
            e
            for e in events
            if e.anchor_id == "xref-alias-BOGON" and e.kind == "added"
        ]
        bogon_removes = [
            e
            for e in events
            if e.anchor_id == "xref-alias-BOGON" and e.kind == "removed"
        ]
        assert len(bogon_adds) == 1
        assert len(bogon_removes) == 1

        inst = s.get(Instance, instance_id)
        assert inst is not None
        assert inst.anchor_events_backfilled_at is not None

    # Rerun — identical result set (truncate-then-insert is idempotent).
    second_count = _reindex_one_instance(session_factory, instance_id, crypto, log)
    assert second_count == first_count

    with session_factory() as s:
        count = s.execute(
            select(AnchorEvent).where(AnchorEvent.instance_id == instance_id)
        ).scalars().all()
        assert len(count) == first_count
