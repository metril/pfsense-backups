"""Cron validation + human description + next-N runs preview."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cron_descriptor import ExpressionDescriptor
from croniter import croniter


def validate(cron: str) -> None:
    """Raise ValueError if ``cron`` isn't a valid 5-field cron expression."""
    if not croniter.is_valid(cron):
        raise ValueError(f"invalid cron expression: {cron!r}")


def validate_tz(tz: str) -> None:
    """Raise ValueError if ``tz`` isn't a known IANA timezone.

    H9: previously a bad tz got all the way into cron_utils.next_runs and
    raised ZoneInfoNotFoundError, which bubbled up as a 500. Router code
    now catches ValueError uniformly.
    """
    try:
        ZoneInfo(tz)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown timezone: {tz!r}") from exc


def resolve_tz(instance_tz: str | None, default_tz: str) -> str:
    """Return the effective timezone for a scheduled job.

    ``instance_tz`` is the per-instance override (``Instance.cron_timezone``);
    ``default_tz`` is the global default (``BackupSettings.default_timezone``).
    Null / empty override falls back to the global.
    """
    return instance_tz or default_tz or "UTC"


def describe(cron: str) -> str:
    try:
        return ExpressionDescriptor(cron, use_24hour_time_format=True).get_description()
    except Exception:
        return ""


def next_runs(cron: str, tz: str = "UTC", count: int = 3) -> list[datetime]:
    validate(cron)
    validate_tz(tz)
    base = datetime.now(ZoneInfo(tz))
    it = croniter(cron, base)
    return [it.get_next(datetime) for _ in range(count)]
