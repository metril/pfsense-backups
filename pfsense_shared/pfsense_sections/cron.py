"""Parses ``<cron>`` — scheduled tasks (pfSense system cron jobs).

Diff key: ``(minute, hour, mday, month, wday, who, command)`` tuple
hashed to a stable string. pfSense doesn't assign an id to cron rows so
we synthesize one from the slots themselves.
"""

from __future__ import annotations

import hashlib
from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from ._helpers import children, text


class CronJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    minute: str | None = None
    hour: str | None = None
    mday: str | None = None
    month: str | None = None
    wday: str | None = None
    who: str | None = None
    command: str | None = None


def _key(fields: tuple[str | None, ...]) -> str:
    blob = "\x1f".join(f or "" for f in fields)
    return hashlib.sha1(blob.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]


def parse(root: Element) -> list[CronJob]:
    cron_el = root.find("cron")
    if cron_el is None:
        return []
    out: list[CronJob] = []
    for item in children(cron_el, "item"):
        fields = (
            text(item, "minute"),
            text(item, "hour"),
            text(item, "mday"),
            text(item, "month"),
            text(item, "wday"),
            text(item, "who"),
            text(item, "command"),
        )
        out.append(
            CronJob(
                key=_key(fields),
                minute=fields[0],
                hour=fields[1],
                mday=fields[2],
                month=fields[3],
                wday=fields[4],
                who=fields[5],
                command=fields[6],
            )
        )
    return out
