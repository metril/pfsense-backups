"""F1 (change-notification trigger) + F5 (config_version capture).

Drives ``PfSenseBackupManager._compute_and_persist_diffs`` over an
in-memory SQLite + fake files (same harness as the ingestion tests) and
asserts the ChangeSummary contract:

- first-ever backup → None (no previous to diff against), and the
  Backup row gets ``config_version`` stamped from the parse;
- changed config → summary with correct counts + labels;
- identical config → None (empty diff never notifies).

Then exercises the Notifier trigger logic with a captured ``_post``:
``change`` rows fire only when a summary is present (status CHANGED,
"Changes:" line in the body, ``changes`` key in the webhook payload);
``send_change_only`` honours instance scoping.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pfsense_shared.backup_diff_storage import ChangeSummary
from pfsense_shared.crypto import Crypto
from pfsense_shared.models import Backup, Base, Instance, Notification
from worker.backup_manager import PfSenseBackupManager
from worker.notifier import Notifier

_XML = """<?xml version="1.0"?>
<pfsense>
  <version>23.3</version>
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


def _setup(tmp_path: Path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    crypto = Crypto(Fernet.generate_key())
    with session_factory() as s:
        inst = Instance(
            name="gw-change",
            url="https://gw.change.test",
            username_ct=crypto.encrypt("admin"),
            password_ct=crypto.encrypt("p"),
            backup_prefix="daily",
        )
        s.add(inst)
        s.commit()
        s.refresh(inst)
        instance_id = inst.id
    manager = PfSenseBackupManager(
        session_factory=session_factory,
        publisher=MagicMock(),
        metrics=MagicMock(),
        crypto=crypto,
        notifier=MagicMock(),
        hostname="test-host",
        instance_locks=MagicMock(),
        cross_process_lock=MagicMock(),
    )
    return session_factory, manager, instance_id, tmp_path


def _seed_backup(session_factory, directory: Path, instance_id, when, content) -> int:
    p = directory / f"daily_{when.isoformat().replace(':', '-')}.xml"
    p.write_bytes(content)
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


def test_first_backup_returns_none_and_stamps_version(tmp_path: Path) -> None:
    session_factory, manager, iid, d = _setup(tmp_path)
    t0 = datetime(2026, 6, 1, tzinfo=UTC)
    b1 = _seed_backup(session_factory, d, iid, t0, _xml("gw", ["A"]))

    summary = manager._compute_and_persist_diffs(b1, iid)

    assert summary is None
    with session_factory() as s:
        assert s.get(Backup, b1).config_version == "23.3"


def test_changed_config_returns_summary(tmp_path: Path) -> None:
    session_factory, manager, iid, d = _setup(tmp_path)
    t0 = datetime(2026, 6, 1, tzinfo=UTC)
    b1 = _seed_backup(session_factory, d, iid, t0, _xml("gw", ["A"]))
    b2 = _seed_backup(
        session_factory, d, iid, t0 + timedelta(days=1), _xml("gw", ["A", "B"])
    )
    manager._compute_and_persist_diffs(b1, iid)

    summary = manager._compute_and_persist_diffs(b2, iid)

    assert summary is not None
    assert summary.added == 1
    assert summary.removed == 0
    assert any("aliases" in label for label in summary.labels)


def test_identical_config_returns_none(tmp_path: Path) -> None:
    session_factory, manager, iid, d = _setup(tmp_path)
    t0 = datetime(2026, 6, 1, tzinfo=UTC)
    same = _xml("gw", ["A"])
    b1 = _seed_backup(session_factory, d, iid, t0, same)
    b2 = _seed_backup(session_factory, d, iid, t0 + timedelta(days=1), same)
    manager._compute_and_persist_diffs(b1, iid)

    assert manager._compute_and_persist_diffs(b2, iid) is None


# --------------------------------------------------------------------- #
# Notifier trigger logic
# --------------------------------------------------------------------- #


def _notifier_setup(trigger: str, *, instance_ids: list[int] | None = None):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    with session_factory() as s:
        crypto = Crypto(Fernet.generate_key())
        inst = Instance(
            name="gw-change",
            url="https://gw.change.test",
            username_ct=crypto.encrypt("a"),
            password_ct=crypto.encrypt("p"),
            backup_prefix="daily",
        )
        s.add(inst)
        s.add(
            Notification(
                name=f"hook-{trigger}",
                kind="webhook",
                url="https://example.test/hook",
                trigger=trigger,
                enabled=True,
                instance_ids_json=(
                    json.dumps(instance_ids) if instance_ids is not None else None
                ),
            )
        )
        s.commit()
    notifier = Notifier(metrics=MagicMock(), hostname="test-host")
    posts: list[tuple[str, dict | None]] = []

    def _capture(hook, url, *, json_body=None, data=None, headers=None):
        posts.append((url, json_body))

    notifier._post = _capture  # type: ignore[method-assign]
    return session_factory, notifier, posts


_SUMMARY = ChangeSummary(added=1, removed=0, modified=2, labels=["aliases: B"])


def test_change_trigger_fires_with_summary() -> None:
    session_factory, notifier, posts = _notifier_setup("change")
    with session_factory() as s:
        notifier.send(
            s,
            is_success=True,
            details="ok",
            succeeded_instances=["gw-change"],
            change_summary=_SUMMARY,
        )
    assert len(posts) == 1
    _url, body = posts[0]
    assert body is not None
    assert "CHANGED" in body["text"]
    assert "Changes: +1 / -0 / ~2" in body["text"]
    assert body["changes"] == {
        "added": 1,
        "removed": 0,
        "modified": 2,
        "labels": ["aliases: B"],
    }


def test_change_trigger_silent_without_summary() -> None:
    session_factory, notifier, posts = _notifier_setup("change")
    with session_factory() as s:
        notifier.send(
            s, is_success=True, details="ok", succeeded_instances=["gw-change"]
        )
        notifier.send(
            s, is_success=False, details="bad", failed_instances=["gw-change"],
            change_summary=_SUMMARY,
        )
    # No-change success: silent. Failure: change rows never fire.
    assert posts == []


def test_success_trigger_message_includes_changes_line() -> None:
    session_factory, notifier, posts = _notifier_setup("success")
    with session_factory() as s:
        notifier.send(
            s,
            is_success=True,
            details="ok",
            succeeded_instances=["gw-change"],
            change_summary=_SUMMARY,
        )
    assert len(posts) == 1
    assert "Changes: +1 / -0 / ~2" in posts[0][1]["text"]


def test_send_change_only_respects_scope() -> None:
    # Scoped to instance id 999 — our instance is id 1, so no fire.
    session_factory, notifier, posts = _notifier_setup(
        "change", instance_ids=[999]
    )
    with session_factory() as s:
        notifier.send_change_only(
            s, instance_name="gw-change", change_summary=_SUMMARY
        )
    assert posts == []

    # Unscoped row fires.
    session_factory, notifier, posts = _notifier_setup("change")
    with session_factory() as s:
        notifier.send_change_only(
            s, instance_name="gw-change", change_summary=_SUMMARY
        )
    assert len(posts) == 1
    assert "CHANGED" in posts[0][1]["text"]
