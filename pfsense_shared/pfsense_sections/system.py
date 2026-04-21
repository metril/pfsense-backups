"""Parses ``<system>`` — hostname, domain, DNS servers, webgui, admin bits.

Sensitive children (webgui cert private keys, `<password>`) are pulled
through the redaction helper.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from ._helpers import bool_flag, children, text


class WebGui(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol: str | None = None
    port: str | None = None
    ssl_certref: str | None = None
    disablehttpredirect: bool = False
    loginautocomplete: bool = False


class SystemInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hostname: str | None = None
    domain: str | None = None
    timezone: str | None = None
    timeservers: list[str] = []
    language: str | None = None
    dnsservers: list[str] = []
    dns_allow_override: bool = False
    dnslocalhost: bool = False
    disablenatreflection: bool = False
    webgui: WebGui | None = None
    # SSH root is scalar (present/absent), we expose just the flag
    enablesshd: bool = False
    sshport: str | None = None
    # Power management policy strings
    powerd_ac_mode: str | None = None
    powerd_battery_mode: str | None = None
    powerd_normal_mode: str | None = None


def _parse_webgui(el: Element | None) -> WebGui | None:
    if el is None:
        return None
    return WebGui(
        protocol=text(el, "protocol"),
        port=text(el, "port"),
        ssl_certref=text(el, "ssl-certref"),
        disablehttpredirect=bool_flag(el, "disablehttpredirect"),
        loginautocomplete=bool_flag(el, "loginautocomplete"),
    )


def parse(root: Element) -> SystemInfo | None:
    sys_el = root.find("system")
    if sys_el is None:
        return None
    # ``<dnsserver>`` is always repeated child elements.
    dnsservers = [e.text or "" for e in children(sys_el, "dnsserver") if (e.text or "").strip()]
    # ``<timeservers>`` has shipped in two shapes across pfSense history:
    #   - pre-2.7:  single <timeservers>0.pool 1.pool</timeservers> (space-joined)
    #   - 2.7+:     multiple <timeservers>0.pool</timeservers> children
    # Accept both so an upgrade from 2.6 → 2.7 doesn't silently drop
    # every NTP peer after the first. If BOTH shapes are present on the
    # same backup (shouldn't happen, but survivable), we merge.
    timeservers_list: list[str] = []
    for el in children(sys_el, "timeservers"):
        raw = (el.text or "").strip()
        if not raw:
            continue
        # A single-child scalar may still contain space-delimited values
        # (legacy layout); split to normalise.
        timeservers_list.extend(raw.split())
    timeservers = timeservers_list
    return SystemInfo(
        hostname=text(sys_el, "hostname"),
        domain=text(sys_el, "domain"),
        timezone=text(sys_el, "timezone"),
        language=text(sys_el, "language"),
        timeservers=timeservers,
        dnsservers=dnsservers,
        dns_allow_override=bool_flag(sys_el, "dnsallowoverride"),
        dnslocalhost=bool_flag(sys_el, "dnslocalhost"),
        disablenatreflection=bool_flag(sys_el, "disablenatreflection"),
        webgui=_parse_webgui(sys_el.find("webgui")),
        enablesshd=bool_flag(sys_el, "enablesshd") or sys_el.find("ssh") is not None,
        sshport=text(sys_el.find("ssh"), "port") if sys_el.find("ssh") is not None else None,
        powerd_ac_mode=text(sys_el, "powerd_ac_mode"),
        powerd_battery_mode=text(sys_el, "powerd_battery_mode"),
        powerd_normal_mode=text(sys_el, "powerd_normal_mode"),
    )
