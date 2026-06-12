"""GFS / age-based retention keep-set computation (F2).

Pure functions over ``(id, started_at)`` pairs so the policy is
unit-testable without the manager, files, or a DB. The worker's
``_cleanup_old_backups`` computes the keep-set here and deletes the
complement.

Semantics (all windows measured back from ``now``):

- ``keep_all_days``     — keep every backup newer than this.
- ``daily_days``        — keep the newest backup per UTC calendar day.
- ``weekly_weeks``      — keep the newest backup per ISO week.
- ``monthly_months``    — keep the newest backup per calendar month
                          (approximated as 31-day blocks for the window
                          bound; bucketing is exact calendar months).
- ``count_cap``         — after tier union, keep at most this many
                          (newest first). This is the legacy
                          ``retention_count`` knob.

All-tiers-``None`` reproduces the legacy behavior exactly: newest
``count_cap`` survive.

Invariants: the newest backup always survives; the keep-set is never
empty when the input isn't.

"Newest per bucket" (not oldest) keeps each bucket's representative
stable as time advances — the bucket only changes when a newer backup
lands in it, never because an older one aged out mid-bucket.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class RetentionPolicy:
    count_cap: int
    keep_all_days: int | None = None
    daily_days: int | None = None
    weekly_weeks: int | None = None
    monthly_months: int | None = None

    @property
    def has_tiers(self) -> bool:
        return any(
            v is not None
            for v in (
                self.keep_all_days,
                self.daily_days,
                self.weekly_weeks,
                self.monthly_months,
            )
        )


def _as_utc(dt: datetime) -> datetime:
    # SQLite hands back naive datetimes; rows are written UTC.
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def compute_keep_ids(
    backups: list[tuple[int, datetime]],
    policy: RetentionPolicy,
    *,
    now: datetime | None = None,
) -> set[int]:
    """IDs of backups to KEEP. ``backups`` is (id, started_at) for the
    instance's *successful* backups, any order."""
    if not backups:
        return set()
    now = _as_utc(now or datetime.now(UTC))
    ordered = sorted(
        ((bid, _as_utc(ts)) for bid, ts in backups),
        key=lambda p: p[1],
        reverse=True,
    )

    if not policy.has_tiers:
        kept = (
            {bid for bid, _ in ordered[: policy.count_cap]}
            if policy.count_cap > 0
            else set()
        )
        # Legacy behavior keeps the literal newest N — but the never-
        # empty invariant still holds for a 0 cap.
        return kept or {ordered[0][0]}

    keep: set[int] = set()

    if policy.keep_all_days is not None:
        cutoff = now - timedelta(days=policy.keep_all_days)
        keep.update(bid for bid, ts in ordered if ts >= cutoff)

    def newest_per_bucket(window_cutoff: datetime, bucket_of) -> None:  # type: ignore[no-untyped-def]
        seen: set[object] = set()
        # ``ordered`` is newest-first, so first hit per bucket = newest.
        for bid, ts in ordered:
            if ts < window_cutoff:
                continue
            b = bucket_of(ts)
            if b in seen:
                continue
            seen.add(b)
            keep.add(bid)

    if policy.daily_days is not None:
        newest_per_bucket(
            now - timedelta(days=policy.daily_days), lambda ts: ts.date()
        )
    if policy.weekly_weeks is not None:
        newest_per_bucket(
            now - timedelta(weeks=policy.weekly_weeks),
            lambda ts: ts.isocalendar()[:2],
        )
    if policy.monthly_months is not None:
        newest_per_bucket(
            now - timedelta(days=31 * policy.monthly_months),
            lambda ts: (ts.year, ts.month),
        )

    # Invariant: newest always survives.
    keep.add(ordered[0][0])

    # Count cap applies after tier union, newest-first.
    if policy.count_cap > 0 and len(keep) > policy.count_cap:
        capped = [bid for bid, _ in ordered if bid in keep][: policy.count_cap]
        keep = set(capped)
        keep.add(ordered[0][0])

    return keep
