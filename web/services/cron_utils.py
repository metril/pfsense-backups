"""Cron validation + human description + next-N runs preview."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from cron_descriptor import ExpressionDescriptor
from croniter import croniter


def validate(cron: str) -> None:
    """Raise ValueError if ``cron`` isn't a valid 5-field cron expression."""
    if not croniter.is_valid(cron):
        raise ValueError(f"invalid cron expression: {cron!r}")


def describe(cron: str) -> str:
    try:
        return ExpressionDescriptor(cron, use_24hour_time_format=True).get_description()
    except Exception:
        return ""


def next_runs(cron: str, tz: str = "UTC", count: int = 3) -> list[datetime]:
    validate(cron)
    base = datetime.now(ZoneInfo(tz))
    it = croniter(cron, base)
    return [it.get_next(datetime) for _ in range(count)]
