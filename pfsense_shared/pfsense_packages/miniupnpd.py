"""Parses miniUPnPd package config under ``<installedpackages><miniupnpd>``.

UPnP-IGD daemon — the "UPnP & NAT-PMP" page under Services. Carries
no credentials; we surface the enable flags, interface bindings, and
allow-rule count so operators can scan for rogue configurations
without cracking the raw XML.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_sections._helpers import bool_flag, text


class MiniUpnpdConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enable: bool = False
    enable_upnp: bool = False
    enable_natpmp: bool = False
    # Comma-separated interface list in the raw XML — we preserve
    # the raw string so operators see exactly what pfSense emitted.
    iface_array: str | None = None
    ext_iface: str | None = None
    download: str | None = None  # kbit/s
    upload: str | None = None
    # Permit / deny rules are stored as repeated ``<permit1>`` …
    # ``<permit4>`` lines with a ``action dest_ip dest_port src_ip``
    # shape; we flatten into a list of the non-empty rules.
    permit_rules: list[str] = []


CONSUMED_TAGS = frozenset({"miniupnpd"})


def parse(ip: Element) -> MiniUpnpdConfig | None:
    el = ip.find("miniupnpd")
    if el is None:
        return None
    permit_rules: list[str] = []
    # Some builds store up to 8 numbered permit slots; newer builds
    # use a repeated ``<permit>`` element. Handle both.
    for slot in range(1, 9):
        rule = text(el, f"permit{slot}")
        if rule:
            permit_rules.append(rule)
    for rule_el in el.findall("permit"):
        if rule_el.text:
            rule = rule_el.text.strip()
            if rule:
                permit_rules.append(rule)
    return MiniUpnpdConfig(
        enable=bool_flag(el, "enable"),
        enable_upnp=bool_flag(el, "enable_upnp"),
        enable_natpmp=bool_flag(el, "enable_natpmp"),
        iface_array=text(el, "iface_array") or text(el, "interface"),
        ext_iface=text(el, "ext_iface") or text(el, "external_interface"),
        download=text(el, "download"),
        upload=text(el, "upload"),
        permit_rules=permit_rules,
    )
