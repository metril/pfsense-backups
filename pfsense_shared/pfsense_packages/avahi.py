"""Parses Avahi package config under ``<installedpackages><avahi>``.

mDNS / Bonjour reflector — bridges multicast DNS across interfaces
so AirPlay, Chromecast, and similar service-discovery traffic works
across segmented VLANs. Carries no credentials.

Field-name mapping to real pfSense Avahi package XML elements
(v0.20.0 renamed ``ipv4_only`` / ``ipv6_only`` to
``ipv4_enabled`` / ``ipv6_enabled`` so the Python field names match
the real on-the-wire ``enable_ipv4`` / ``enable_ipv6`` tag names):
  ``<enable>``              → ``enable``
  ``<enable_reflector>``    → ``reflector``
  ``<enable_ipv4>``         → ``ipv4_enabled``
  ``<enable_ipv6>``         → ``ipv6_enabled``
  ``<enable_wide_area>``    → ``wide_area``
  ``<publish_workstation>`` → ``publish_workstation``
  ``<publish_addresses>``   → ``publish_addresses``
  ``<reflect_ipv>``         → ``reflect_ipv``
  ``<interfaces>``          → ``interfaces``
  ``<denyinterfaces>``      → ``allow_deny_interfaces``
  ``<cache_entries_max>``   → ``cache_entries_max``
  ``<browsedomains>``       → ``browse_domains``
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_sections._helpers import bool_flag, text


class AvahiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enable: bool = False
    reflector: bool = False
    ipv4_enabled: bool = False
    ipv6_enabled: bool = False
    wide_area: bool = False
    publish_workstation: bool = False
    publish_addresses: bool = False
    # ``"ipv4"``, ``"ipv6"``, or ``"ipv4,ipv6"``; free-form on older builds.
    reflect_ipv: str | None = None
    # Comma-separated interface list as stored by pfSense.
    interfaces: str | None = None
    allow_deny_interfaces: str | None = None
    cache_entries_max: str | None = None
    browse_domains: str | None = None


CONSUMED_TAGS = frozenset({"avahi"})


def parse(ip: Element) -> AvahiConfig | None:
    el = ip.find("avahi")
    if el is None:
        return None
    return AvahiConfig(
        enable=bool_flag(el, "enable"),
        reflector=bool_flag(el, "enable_reflector") or bool_flag(el, "reflector"),
        # Prefer the real XML tag (``enable_ipv4``); keep the legacy
        # ``ipv4_only`` read so older fixtures / forks still parse.
        ipv4_enabled=bool_flag(el, "enable_ipv4") or bool_flag(el, "ipv4_only"),
        ipv6_enabled=bool_flag(el, "enable_ipv6") or bool_flag(el, "ipv6_only"),
        wide_area=bool_flag(el, "enable_wide_area"),
        publish_workstation=bool_flag(el, "publish_workstation"),
        publish_addresses=bool_flag(el, "publish_addresses"),
        reflect_ipv=text(el, "reflect_ipv"),
        interfaces=text(el, "interfaces") or text(el, "iface_array"),
        allow_deny_interfaces=text(el, "denyinterfaces"),
        cache_entries_max=text(el, "cache_entries_max"),
        browse_domains=text(el, "browsedomains"),
    )
