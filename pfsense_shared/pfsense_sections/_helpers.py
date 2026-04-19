"""Small XML helpers shared by every section parser.

Kept deliberately minimal — each function is a few lines, but lifting
them out of the section modules removes a lot of repeated boilerplate
and gives redaction a single choke point.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from xml.etree.ElementTree import Element

from pfsense_shared.pfsense_redact import redact


def text(el: Element | None, tag: str, default: str | None = None) -> str | None:
    """Return the text of ``el/<tag>`` or ``default`` if missing/empty.

    pfSense uses self-closing elements for "field is present but
    empty" (e.g. ``<dhcpd><lan><enable/></lan></dhcpd>``). Treat those
    as an empty string — the caller's ``bool_flag`` helper converts
    that to ``True`` because pfSense's convention is "tag present ⇒ on".
    """
    if el is None:
        return default
    sub = el.find(tag)
    if sub is None:
        return default
    if sub.text is None:
        return ""
    return sub.text


def redacted_text(el: Element | None, tag: str) -> str | None:
    """Like ``text`` but routes the result through the redaction rules."""
    return redact(tag, text(el, tag))


def bool_flag(el: Element | None, tag: str) -> bool:
    """pfSense booleans: tag present (even empty) ⇒ True, absent ⇒ False."""
    if el is None:
        return False
    return el.find(tag) is not None


def children(el: Element | None, tag: str) -> list[Element]:
    """List-of-items helper — safe against ``None`` parent."""
    if el is None:
        return []
    return list(el.findall(tag))


def strip_empty(d: dict[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is ``None`` or an empty string.

    Keeps Pydantic output stable (same key-set whether or not the
    source had the tag) while keeping the JSON small. ``0``, ``False``,
    and empty lists are kept — they carry meaning.
    """
    return {k: v for k, v in d.items() if v not in (None, "")}


def to_list(items: Iterable[Any]) -> list[Any]:
    """Small adapter so generator-style section parsers stay readable."""
    return list(items)
