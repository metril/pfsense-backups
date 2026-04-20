"""Parses Suricata IDS/IPS config under ``<installedpackages>``.

Per-interface rule sets live under ``<suricata><rule><item>…``; each
interface has its own enable / categories / action defaults. Pass
lists (``<passlist>``) and IP reputation lists (``<iplist>``) are
separate sibling tags.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_sections._helpers import bool_flag, children, text


class SuricataInterface(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uuid: str
    interface: str | None = None
    descr: str | None = None
    enable: bool = False
    blockoffenders7: bool = False  # "Block offenders" flag
    ips_mode: str | None = None
    eve_enable: bool = False
    # Flattened rule category enable list (one string per enabled category).
    categories: list[str] = []


class SuricataPasslistEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Stable key: address + descr (there's no explicit id).
    key: str
    address: str | None = None
    descr: str | None = None


class SuricataPasslist(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    descr: str | None = None
    entries: list[SuricataPasslistEntry] = []


class SuricataConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enable_stats: bool = False
    oinkmaster_configured: bool = False  # oinkcode / Emerging Threats key set
    interfaces: list[SuricataInterface] = []
    passlists: list[SuricataPasslist] = []


CONSUMED_TAGS = frozenset(
    {
        "suricata",
        "suricatapasslist",
    }
)


def _category_list(item: Element) -> list[str]:
    # pfSense stores enabled categories under ``<rulesets>`` as a ``||``
    # separated string. A couple of install variants use repeated
    # ``<category>`` children instead; handle both.
    raw = text(item, "rulesets") or ""
    if raw:
        return [x for x in raw.split("||") if x]
    return [e.text for e in children(item, "category") if e.text]


def parse(ip: Element) -> SuricataConfig | None:
    root = ip.find("suricata")
    passlist_root = ip.find("suricatapasslist")

    if root is None and passlist_root is None:
        return None

    interfaces: list[SuricataInterface] = []
    if root is not None:
        # Some pfSense versions use <rule><item> (per-interface config
        # under a "rule" container); others use <suricataconfig>.
        rule_el = root.find("rule")
        if rule_el is None:
            rule_el = root.find("suricataconfig")
        if rule_el is not None:
            for item in children(rule_el, "item"):
                uuid = text(item, "uuid") or text(item, "interface") or "?"
                interfaces.append(
                    SuricataInterface(
                        uuid=uuid,
                        interface=text(item, "interface"),
                        descr=text(item, "descr"),
                        enable=bool_flag(item, "enable"),
                        blockoffenders7=bool_flag(item, "blockoffenders7"),
                        ips_mode=text(item, "ips_mode"),
                        eve_enable=bool_flag(item, "eve_log_enabled"),
                        categories=_category_list(item),
                    )
                )

    passlists: list[SuricataPasslist] = []
    if passlist_root is not None:
        for item in children(passlist_root, "item"):
            name = text(item, "name")
            if not name:
                continue
            entries: list[SuricataPasslistEntry] = []
            row_el = item.find("row")
            if row_el is not None:
                for row in children(row_el, "item") or children(item, "row"):
                    addr = text(row, "ipaddress") or text(row, "address")
                    if addr:
                        entries.append(
                            SuricataPasslistEntry(
                                key=f"{addr}|{text(row, 'descr') or ''}",
                                address=addr,
                                descr=text(row, "descr"),
                            )
                        )
            passlists.append(
                SuricataPasslist(
                    name=name,
                    descr=text(item, "descr"),
                    entries=entries,
                )
            )

    oinkmaster_configured = False
    if root is not None:
        # The Emerging Threats / Snort-VRT oink code is a credential;
        # report "configured" vs not instead of surfacing the value.
        oinkmaster_configured = bool(
            (text(root, "oinkcode") or text(root, "snortcommunityrules") or "").strip()
        )

    return SuricataConfig(
        enable_stats=bool_flag(root, "enable_stats_collection")
        if root is not None
        else False,
        oinkmaster_configured=oinkmaster_configured,
        interfaces=interfaces,
        passlists=passlists,
    )
