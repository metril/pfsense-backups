"""Parses ``<aliases>`` — host / network / port / url aliases."""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from ._helpers import children, text


class Alias(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: str | None = None  # host | network | port | url | urltable | ...
    descr: str | None = None
    # Addresses are space-separated in the raw XML; we normalize to a
    # list so the diff can detect "one host added" vs "full list changed".
    entries: list[str] = []
    # Per-entry descriptions parallel the entries list (pfSense stores them
    # pipe-separated in ``<detail>``).
    details: list[str] = []
    # urltable — update frequency (days).
    updatefreq: str | None = None


def parse(root: Element) -> list[Alias]:
    el = root.find("aliases")
    if el is None:
        return []
    out: list[Alias] = []
    for item in children(el, "alias"):
        name = text(item, "name")
        if not name:
            continue
        address_raw = text(item, "address") or ""
        details_raw = text(item, "detail") or ""
        out.append(
            Alias(
                name=name,
                type=text(item, "type"),
                descr=text(item, "descr"),
                entries=address_raw.split() if address_raw else [],
                details=details_raw.split("||") if details_raw else [],
                updatefreq=text(item, "updatefreq"),
            )
        )
    return out
