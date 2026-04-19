"""Parses ``<sysctl>`` — kernel / networking tunables."""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from ._helpers import children, text


class SysctlTunable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Stable key for diff matching: tunable name.
    tunable: str
    value: str | None = None
    descr: str | None = None


def parse(root: Element) -> list[SysctlTunable]:
    el = root.find("sysctl")
    if el is None:
        return []
    out: list[SysctlTunable] = []
    for item in children(el, "item"):
        name = text(item, "tunable")
        if not name:
            continue
        out.append(
            SysctlTunable(
                tunable=name,
                value=text(item, "value"),
                descr=text(item, "descr"),
            )
        )
    return out
