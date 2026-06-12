"""Periodic staleness check (F6): alert when an enabled, scheduled
instance has no recent successful backup.

Runs from an APScheduler interval job (see ``Scheduler.start``). All
clock reads come in through the ``now`` parameter so tests drive time
explicitly.

Threshold semantics:
- ``Instance.stale_after_hours`` set → use it verbatim.
- NULL → auto-derive: 2× the gap between the next two cron fires
  (croniter), floored at 1 hour. Irregular crons that want different
  slack set the explicit override.
- Instances that are disabled or have no cron_expression are skipped —
  no schedule means no staleness expectation. Their gauge is cleared.

Suppression: ``Instance.stale_notified_at`` is stamped when an alert
fires; re-alerts wait ``RENOTIFY_HOURS``. The stamp is cleared (and a
recovery notification sent) by the next successful backup — see
``PfSenseBackupManager.backup_instance``.

Notification routing: rows with trigger ``stale`` or ``always``,
except kind=healthchecks — Healthchecks pings are themselves a
staleness detector (missed-ping alerts), so double-reporting through
them would mark the *backup* check failed over a scheduling gap.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from croniter import croniter
from sqlalchemy import func, select

from pfsense_shared.models import Backup, Instance

if TYPE_CHECKING:
    from .notifier import Notifier
    from .prometheus_metrics import PrometheusMetrics

log = logging.getLogger(__name__)

CHECK_INTERVAL_MINUTES = 15
RENOTIFY_HOURS = 24.0
_FLOOR_HOURS = 1.0
_AUTO_MULTIPLIER = 2.0


def derive_threshold_hours(
    cron_expression: str, explicit_hours: int | None, *, now: datetime
) -> float | None:
    """Hours of silence after which the instance counts as stale.

    Explicit override wins. Otherwise 2× the cron cadence (gap between
    the next two fires from ``now``), floored at 1h. Returns None when
    the cron expression is invalid — the schedule loader already logs
    that loudly; staleness just skips."""
    if explicit_hours is not None:
        return float(explicit_hours)
    try:
        it = croniter(cron_expression, now)
        first: datetime = it.get_next(datetime)
        second: datetime = it.get_next(datetime)
    except (ValueError, KeyError) as exc:
        log.debug("staleness: cron %r unusable: %s", cron_expression, exc)
        return None
    gap_hours = (second - first).total_seconds() / 3600.0
    return max(gap_hours * _AUTO_MULTIPLIER, _FLOOR_HOURS)


def check_stale_instances(
    session_factory: Any,
    notifier: Notifier,
    metrics: PrometheusMetrics | None,
    *,
    now: datetime | None = None,
) -> list[int]:
    """One sweep over all instances; returns ids alerted this pass
    (test convenience). Reference point for "silence" is the newest
    successful backup, falling back to ``Instance.created_at`` so an
    instance that has never succeeded still goes stale."""
    now = now or datetime.now(UTC)
    alerted: list[int] = []
    with session_factory() as s:
        instances = s.execute(select(Instance)).scalars().all()
        for inst in instances:
            if not inst.enabled or not inst.cron_expression:
                if metrics is not None:
                    metrics.set_instance_stale(inst.name, False)
                continue
            threshold = derive_threshold_hours(
                inst.cron_expression, inst.stale_after_hours, now=now
            )
            if threshold is None:
                continue
            last_ok = s.execute(
                select(func.max(Backup.started_at)).where(
                    Backup.instance_id == inst.id,
                    Backup.success.is_(True),
                )
            ).scalar_one_or_none()
            reference = last_ok or inst.created_at
            if reference is not None and reference.tzinfo is None:
                # SQLite returns naive datetimes; rows are written UTC.
                reference = reference.replace(tzinfo=UTC)
            is_stale = reference is None or (
                now - reference > timedelta(hours=threshold)
            )
            if metrics is not None:
                metrics.set_instance_stale(inst.name, is_stale)
            if not is_stale:
                continue

            notified = inst.stale_notified_at
            if notified is not None and notified.tzinfo is None:
                notified = notified.replace(tzinfo=UTC)
            if notified is not None and (
                now - notified < timedelta(hours=RENOTIFY_HOURS)
            ):
                continue

            silent_hours = (
                (now - reference).total_seconds() / 3600.0
                if reference is not None
                else float("inf")
            )
            detail = (
                f"No successful backup for '{inst.name}' in "
                f"{silent_hours:.1f}h (threshold {threshold:.1f}h)."
            )
            log.warning("staleness: %s", detail)
            try:
                notifier.send_stale(
                    s,
                    instance_id=inst.id,
                    instance_name=inst.name,
                    detail=detail,
                    is_recovery=False,
                )
            except Exception as exc:
                log.error("staleness notification failed: %s", exc)
            inst.stale_notified_at = now
            alerted.append(inst.id)
        s.commit()
    return alerted
