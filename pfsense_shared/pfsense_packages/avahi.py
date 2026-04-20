"""Parses Avahi package config under ``<installedpackages><avahi>``.

mDNS / Bonjour reflector — bridges multicast DNS across interfaces
so AirPlay, Chromecast, and similar service-discovery traffic works
across segmented VLANs. Carries no credentials.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_sections._helpers import bool_flag, text


class AvahiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enable: bool = False
    reflector: bool = False
    # Newer Avahi packages expose a "forward to unicast" mode.
    ipv4_only: bool = False
    ipv6_only: bool = False
    # Comma-separated interface list as stored by pfSense.
    interfaces: str | None = None
    allow_deny_interfaces: str | None = None
    cache_entries_max: str | None = None


CONSUMED_TAGS = frozenset({"avahi"})


def parse(ip: Element) -> AvahiConfig | None:
    el = ip.find("avahi")
    if el is None:
        return None
    return AvahiConfig(
        enable=bool_flag(el, "enable"),
        reflector=bool_flag(el, "enable_reflector") or bool_flag(el, "reflector"),
        ipv4_only=bool_flag(el, "ipv4_only"),
        ipv6_only=bool_flag(el, "ipv6_only"),
        interfaces=text(el, "interfaces") or text(el, "iface_array"),
        allow_deny_interfaces=text(el, "denyinterfaces"),
        cache_entries_max=text(el, "cache_entries_max"),
    )
