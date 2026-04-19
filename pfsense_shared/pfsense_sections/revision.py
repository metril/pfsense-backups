"""Parses ``<revision>`` — config-revision metadata.

Useful as the header row on the structured view: when the config was
last written, by whom, and why.
"""

from __future__ import annotations

from datetime import UTC, datetime
from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from ._helpers import text


class Revision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time: datetime | None = None
    description: str | None = None
    username: str | None = None


def parse(root: Element) -> Revision | None:
    el = root.find("revision")
    if el is None:
        return None
    ts_raw = text(el, "time")
    ts: datetime | None = None
    if ts_raw and ts_raw.strip().isdigit():
        # pfSense stores unix seconds.
        ts = datetime.fromtimestamp(int(ts_raw.strip()), tz=UTC)
    return Revision(
        time=ts,
        description=text(el, "description"),
        username=text(el, "username"),
    )
