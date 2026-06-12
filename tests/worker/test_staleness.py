"""F6 staleness sweep: fire / suppress / renotify / recovery, plus the
croniter threshold derivation. The clock is always injected via
``now=``; the notifier is a recording stub.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pfsense_shared.crypto import Crypto
from pfsense_shared.models import Backup, Base, Instance
from worker.staleness import (
    RENOTIFY_HOURS,
    check_stale_instances,
    derive_threshold_hours,
)

NOW = datetime(2026, 6, 12, 12, 0, tzinfo=UTC)


# ------------------------- threshold derivation ------------------------- #


def test_explicit_threshold_wins() -> None:
    assert derive_threshold_hours("0 * * * *", 48, now=NOW) == 48.0


def test_auto_threshold_is_twice_cron_gap() -> None:
    # Daily cron → 24h gap → 48h threshold.
    assert derive_threshold_hours("0 3 * * *", None, now=NOW) == 48.0


def test_auto_threshold_floors_at_one_hour() -> None:
    # Every-5-minutes cron → 10min × 2 < 1h floor.
    assert derive_threshold_hours("*/5 * * * *", None, now=NOW) == 1.0


def test_invalid_cron_returns_none() -> None:
    assert derive_threshold_hours("not a cron", None, now=NOW) is None


# ----------------------------- sweep logic ------------------------------ #


class _RecordingNotifier:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def send_stale(self, _session, **kwargs) -> None:
        self.calls.append(kwargs)


def _setup(
    *,
    cron: str | None = "0 3 * * *",
    enabled: bool = True,
    stale_after_hours: int | None = None,
    last_ok_age_hours: float | None = None,
    stale_notified_age_hours: float | None = None,
):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    crypto = Crypto(Fernet.generate_key())
    with session_factory() as s:
        inst = Instance(
            name="gw-stale",
            url="https://gw.stale.test",
            username_ct=crypto.encrypt("a"),
            password_ct=crypto.encrypt("p"),
            backup_prefix="daily",
            cron_expression=cron,
            enabled=enabled,
            stale_after_hours=stale_after_hours,
            stale_notified_at=(
                NOW - timedelta(hours=stale_notified_age_hours)
                if stale_notified_age_hours is not None
                else None
            ),
            created_at=NOW - timedelta(days=30),
        )
        s.add(inst)
        s.commit()
        s.refresh(inst)
        iid = inst.id
        if last_ok_age_hours is not None:
            when = NOW - timedelta(hours=last_ok_age_hours)
            s.add(
                Backup(
                    instance_id=iid,
                    started_at=when,
                    finished_at=when,
                    duration_seconds=1.0,
                    filename="x.xml",
                    path="/tmp/x.xml",
                    size_bytes=1,
                    compressed=False,
                    success=True,
                    encrypted=False,
                )
            )
            s.commit()
    return session_factory, iid


def test_fresh_backup_does_not_alert() -> None:
    session_factory, _ = _setup(last_ok_age_hours=2)
    notifier = _RecordingNotifier()
    alerted = check_stale_instances(session_factory, notifier, None, now=NOW)
    assert alerted == []
    assert notifier.calls == []


def test_stale_backup_alerts_and_stamps() -> None:
    # Daily cron → auto threshold 48h; last success 72h ago.
    session_factory, iid = _setup(last_ok_age_hours=72)
    notifier = _RecordingNotifier()
    alerted = check_stale_instances(session_factory, notifier, None, now=NOW)
    assert alerted == [iid]
    assert len(notifier.calls) == 1
    assert notifier.calls[0]["is_recovery"] is False
    with session_factory() as s:
        assert s.get(Instance, iid).stale_notified_at is not None


def test_recent_alert_is_suppressed() -> None:
    session_factory, _ = _setup(
        last_ok_age_hours=72, stale_notified_age_hours=2
    )
    notifier = _RecordingNotifier()
    assert check_stale_instances(session_factory, notifier, None, now=NOW) == []
    assert notifier.calls == []


def test_renotify_after_window() -> None:
    session_factory, iid = _setup(
        last_ok_age_hours=72, stale_notified_age_hours=RENOTIFY_HOURS + 1
    )
    notifier = _RecordingNotifier()
    assert check_stale_instances(session_factory, notifier, None, now=NOW) == [iid]


def test_disabled_or_unscheduled_skipped() -> None:
    for kwargs in ({"enabled": False}, {"cron": None}):
        session_factory, _ = _setup(last_ok_age_hours=500, **kwargs)  # type: ignore[arg-type]
        notifier = _RecordingNotifier()
        assert (
            check_stale_instances(session_factory, notifier, None, now=NOW) == []
        )


def test_never_succeeded_instance_goes_stale_via_created_at() -> None:
    # No successful backup at all; created_at is 30 days back.
    session_factory, iid = _setup(last_ok_age_hours=None)
    notifier = _RecordingNotifier()
    assert check_stale_instances(session_factory, notifier, None, now=NOW) == [iid]


def test_explicit_threshold_overrides_auto() -> None:
    # 200h explicit threshold; 72h silence → not stale.
    session_factory, _ = _setup(last_ok_age_hours=72, stale_after_hours=200)
    notifier = _RecordingNotifier()
    assert check_stale_instances(session_factory, notifier, None, now=NOW) == []


def test_gauge_is_set() -> None:
    session_factory, _ = _setup(last_ok_age_hours=72)
    metrics = MagicMock()
    check_stale_instances(session_factory, _RecordingNotifier(), metrics, now=NOW)
    metrics.set_instance_stale.assert_called_once_with("gw-stale", True)


# ------------------------- send_stale routing --------------------------- #


def test_send_stale_routes_to_stale_and_always_only() -> None:
    from pfsense_shared.models import Notification
    from worker.notifier import Notifier

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    with session_factory() as s:
        for name, trigger, kind in (
            ("h-stale", "stale", "webhook"),
            ("h-always", "always", "webhook"),
            ("h-failure", "failure", "webhook"),
            ("h-change", "change", "webhook"),
            # Healthchecks is its own staleness detector — excluded.
            ("h-hc", "always", "healthchecks"),
        ):
            s.add(
                Notification(
                    name=name, kind=kind, url=f"https://x.test/{name}",
                    trigger=trigger, enabled=True,
                )
            )
        s.commit()

    notifier = Notifier(metrics=MagicMock(), hostname="t")
    fired: list[str] = []
    notifier._post = lambda hook, url, **kw: fired.append(hook.name)  # type: ignore[method-assign]

    with session_factory() as s:
        notifier.send_stale(
            s, instance_id=1, instance_name="gw", detail="d", is_recovery=False
        )
    assert sorted(fired) == ["h-always", "h-stale"]
