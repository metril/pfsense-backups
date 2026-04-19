"""Parses ``<virtualip>`` (CARP / IP alias / proxy-ARP) and ``<hasync>``.

CARP VHIDs and HA pfsync config are prime change-review targets —
getting them wrong silently breaks failover.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact

from ._helpers import bool_flag, children, text


class VirtualIP(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Stable key: ``<uniqid>`` when present, else mode+subnet+vhid.
    key: str
    mode: str | None = None  # "carp" | "ipalias" | "proxyarp" | "other"
    interface: str | None = None
    subnet: str | None = None
    subnet_bits: str | None = None
    vhid: str | None = None
    advbase: str | None = None
    advskew: str | None = None
    descr: str | None = None
    # CARP password — redacted (pfSense uses <password> here too).
    password: str | None = None


class HaSync(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # pfsync — state synchronisation
    pfsyncenabled: bool = False
    pfsyncinterface: str | None = None
    pfsyncpeerip: str | None = None
    # XMLRPC sync — config replication
    synchronizetoip: str | None = None
    username: str | None = None
    password: str | None = None  # redacted
    # Granular toggles: which areas are synced. pfSense represents each
    # as a string tag present when enabled.
    synchronizerules: bool = False
    synchronizenat: bool = False
    synchronizealiases: bool = False
    synchronizeschedules: bool = False
    synchronizedhcpd: bool = False
    synchronizedhcrelay: bool = False
    synchronizedns: bool = False
    synchronizeopenvpn: bool = False
    synchronizeipsec: bool = False
    synchronizeusers: bool = False
    synchronizeauthservers: bool = False
    synchronizecerts: bool = False


def parse_virtualips(root: Element) -> list[VirtualIP]:
    el = root.find("virtualip")
    if el is None:
        return []
    out: list[VirtualIP] = []
    for v in children(el, "vip"):
        mode = text(v, "mode")
        uniqid = text(v, "uniqid")
        subnet = text(v, "subnet")
        vhid = text(v, "vhid")
        key = uniqid or f"{mode or '?'}|{subnet or '?'}|{vhid or ''}"
        out.append(
            VirtualIP(
                key=key,
                mode=mode,
                interface=text(v, "interface"),
                subnet=subnet,
                subnet_bits=text(v, "subnet_bits"),
                vhid=vhid,
                advbase=text(v, "advbase"),
                advskew=text(v, "advskew"),
                descr=text(v, "descr"),
                password=redact("password", text(v, "password")),
            )
        )
    return out


def parse_hasync(root: Element) -> HaSync | None:
    el = root.find("hasync")
    if el is None:
        return None
    return HaSync(
        pfsyncenabled=text(el, "pfsyncenabled") in ("on", "yes", "1"),
        pfsyncinterface=text(el, "pfsyncinterface"),
        pfsyncpeerip=text(el, "pfsyncpeerip"),
        synchronizetoip=text(el, "synchronizetoip"),
        username=text(el, "username"),
        password=redact("password", text(el, "password")),
        synchronizerules=bool_flag(el, "synchronizerules"),
        synchronizenat=bool_flag(el, "synchronizenat"),
        synchronizealiases=bool_flag(el, "synchronizealiases"),
        synchronizeschedules=bool_flag(el, "synchronizeschedules"),
        synchronizedhcpd=bool_flag(el, "synchronizedhcpd"),
        synchronizedhcrelay=bool_flag(el, "synchronizedhcrelay"),
        synchronizedns=bool_flag(el, "synchronizednsforwarder")
        or bool_flag(el, "synchronizednsresolver"),
        synchronizeopenvpn=bool_flag(el, "synchronizeopenvpn"),
        synchronizeipsec=bool_flag(el, "synchronizeipsec"),
        synchronizeusers=bool_flag(el, "synchronizeusers"),
        synchronizeauthservers=bool_flag(el, "synchronizeauthservers"),
        synchronizecerts=bool_flag(el, "synchronizecerts"),
    )
