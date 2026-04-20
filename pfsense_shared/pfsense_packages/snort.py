"""Parses Snort IDS/IPS config under ``<installedpackages>``.

Sibling of Suricata — older installs use Snort, newer ones tend to
use Suricata. The XML shape is very similar: a top-level ``<snort>``
with a ``<rule><item>`` sub-element per monitored interface, plus
per-package settings stored under a ``<snortglobal>`` block for
oinkcode / rule-download credentials.

Redaction: the subscriber ``oinkcode`` is already in ``_EXACT``; we
never expose it, only a ``oinkmaster_configured`` boolean. The same
treatment covers the Snort-VRT subscription hash.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_sections._helpers import bool_flag, children, text


class SnortInterface(BaseModel):
    """One Snort-monitored interface. Fields mirror
    ``SuricataInterface`` so the UI can render both with one
    component shape."""

    model_config = ConfigDict(extra="forbid")

    uuid: str
    interface: str | None = None
    descr: str | None = None
    enable: bool = False
    # Matches ``SuricataInterface.blockoffenders7`` so the UI can
    # render Snort + Suricata interfaces through the same shape. The
    # XML tag is literally ``<blockoffenders7>`` (a historical
    # pfSense quirk — the "7" is a leftover version suffix).
    blockoffenders7: bool = False
    ips_mode: str | None = None
    # Snort stores its enabled rulesets the same way Suricata does —
    # either as a ``||``-separated ``<rulesets>`` string or as
    # repeated ``<category>`` children.
    categories: list[str] = []


class SnortConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # From ``<snortglobal>`` — global package state.
    oinkmaster_configured: bool = False  # VRT or ET subscription key set
    snort_community_rules_enabled: bool = False
    emerging_threats_enabled: bool = False
    # From ``<snort><rule>`` — one entry per monitored interface.
    interfaces: list[SnortInterface] = []


CONSUMED_TAGS = frozenset(
    {
        "snort",
        "snortglobal",
    }
)


def _category_list(item: Element) -> list[str]:
    # Same shape as Suricata: ``<rulesets>`` is ``||``-separated, or
    # repeated ``<category>`` children.
    raw = text(item, "rulesets") or ""
    if raw:
        return [x for x in raw.split("||") if x]
    return [e.text for e in children(item, "category") if e.text]


def parse(ip: Element) -> SnortConfig | None:
    root = ip.find("snort")
    global_el = ip.find("snortglobal")
    if root is None and global_el is None:
        return None

    interfaces: list[SnortInterface] = []
    if root is not None:
        rule_el = root.find("rule")
        if rule_el is not None:
            for item in children(rule_el, "item"):
                uuid = text(item, "uuid") or text(item, "interface") or "?"
                interfaces.append(
                    SnortInterface(
                        uuid=uuid,
                        interface=text(item, "interface"),
                        descr=text(item, "descr"),
                        enable=bool_flag(item, "enable"),
                        blockoffenders7=bool_flag(item, "blockoffenders7")
                        or bool_flag(item, "blockoffenders"),
                        ips_mode=text(item, "ips_mode"),
                        categories=_category_list(item),
                    )
                )

    oinkmaster_configured = False
    community = False
    et_enabled = False
    if global_el is not None:
        oinkmaster_configured = bool((text(global_el, "oinkcode") or "").strip())
        community = bool_flag(global_el, "snortcommunityrules")
        et_enabled = bool_flag(global_el, "emergingthreats") or bool_flag(
            global_el, "emerging_threats"
        )

    return SnortConfig(
        oinkmaster_configured=oinkmaster_configured,
        snort_community_rules_enabled=community,
        emerging_threats_enabled=et_enabled,
        interfaces=interfaces,
    )
