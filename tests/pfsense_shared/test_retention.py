"""GFS keep-set computation (F2) — pure-function table tests.

Timestamps are synthetic; ``now`` is always injected so the buckets
are deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pfsense_shared.retention import RetentionPolicy, compute_keep_ids

NOW = datetime(2026, 6, 12, 12, 0, tzinfo=UTC)


def _series(count: int, *, step: timedelta, start: datetime | None = None):
    """(id, ts) newest-first: id 1 is the newest backup."""
    start = start or NOW
    return [(i + 1, start - step * i) for i in range(count)]


def test_no_tiers_is_legacy_count_behavior() -> None:
    backups = _series(10, step=timedelta(days=1))
    keep = compute_keep_ids(backups, RetentionPolicy(count_cap=3), now=NOW)
    assert keep == {1, 2, 3}


def test_empty_input_keeps_nothing() -> None:
    assert compute_keep_ids([], RetentionPolicy(count_cap=3), now=NOW) == set()


def test_zero_cap_without_tiers_still_keeps_newest() -> None:
    backups = _series(5, step=timedelta(days=1))
    keep = compute_keep_ids(backups, RetentionPolicy(count_cap=0), now=NOW)
    assert keep == {1}


def test_keep_all_window() -> None:
    backups = _series(10, step=timedelta(days=1))
    policy = RetentionPolicy(count_cap=100, keep_all_days=3)
    keep = compute_keep_ids(backups, policy, now=NOW)
    # Newer than 3 days: ids 1..3 (0,1,2 days old) — id 4 is exactly
    # 3 days old and ``>= cutoff`` keeps it too.
    assert {1, 2, 3, 4} <= keep
    assert 6 not in keep


def test_daily_tier_keeps_newest_per_day() -> None:
    # 4 backups across 2 days (2 per day), hourly cadence.
    day0 = NOW
    backups = [
        (1, day0),
        (2, day0 - timedelta(hours=2)),
        (3, day0 - timedelta(days=1)),
        (4, day0 - timedelta(days=1, hours=2)),
    ]
    policy = RetentionPolicy(count_cap=100, daily_days=7)
    keep = compute_keep_ids(backups, policy, now=NOW)
    assert keep == {1, 3}  # newest per calendar day


def test_weekly_tier_keeps_newest_per_iso_week() -> None:
    backups = _series(28, step=timedelta(days=1))
    policy = RetentionPolicy(count_cap=100, weekly_weeks=4)
    keep = compute_keep_ids(backups, policy, now=NOW)
    # One per ISO week over ~4 weeks (+ the always-keep-newest, which
    # is already a bucket representative).
    assert 1 in keep
    assert 4 <= len(keep) <= 6
    kept_weeks = {ts.isocalendar()[:2] for bid, ts in backups if bid in keep}
    assert len(kept_weeks) == len(keep)  # one representative per week


def test_monthly_tier_keeps_newest_per_month() -> None:
    backups = _series(90, step=timedelta(days=1))
    policy = RetentionPolicy(count_cap=100, monthly_months=3)
    keep = compute_keep_ids(backups, policy, now=NOW)
    kept_months = {(ts.year, ts.month) for bid, ts in backups if bid in keep}
    assert len(kept_months) == len(keep)
    assert 3 <= len(keep) <= 4


def test_tiers_union_and_cap() -> None:
    backups = _series(60, step=timedelta(days=1))
    policy = RetentionPolicy(
        count_cap=5, keep_all_days=2, daily_days=14, monthly_months=2
    )
    keep = compute_keep_ids(backups, policy, now=NOW)
    assert len(keep) == 5  # cap wins over the larger union
    assert 1 in keep  # newest always survives


def test_newest_always_survives_even_outside_all_windows() -> None:
    # A single ancient backup: outside every window.
    backups = [(42, NOW - timedelta(days=400))]
    policy = RetentionPolicy(
        count_cap=10, keep_all_days=1, daily_days=7, weekly_weeks=4
    )
    keep = compute_keep_ids(backups, policy, now=NOW)
    assert keep == {42}


def test_naive_datetimes_are_treated_as_utc() -> None:
    backups = [(1, NOW.replace(tzinfo=None)), (2, (NOW - timedelta(days=2)).replace(tzinfo=None))]
    policy = RetentionPolicy(count_cap=10, keep_all_days=1)
    keep = compute_keep_ids(backups, policy, now=NOW)
    assert 1 in keep
