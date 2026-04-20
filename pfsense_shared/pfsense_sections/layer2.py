"""Parses L2 configs: VLANs, bridges, GIF / GRE tunnels, PPP, QinQ, WOL.

All of these live under their own top-level tag in config.xml. Each
section returns a list of Pydantic items with a stable diff key —
interface name for VLANs/bridges/PPP, ``network`` for WOL, etc.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from ._helpers import bool_flag, children, text


class Vlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Stable key: parent device + tag uniquely identify a VLAN.
    key: str
    if_: str | None = None  # parent interface
    tag: str | None = None  # 802.1Q tag
    pcp: str | None = None  # 802.1p priority
    vlanif: str | None = None  # synthesized device (em0.100)
    descr: str | None = None


class Bridge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Stable key: bridge device name (bridge0, bridge1, …).
    bridgeif: str
    members: list[str] = []
    descr: str | None = None
    # STP toggle (present ⇒ enabled)
    enablestp: bool = False


class Tunnel(BaseModel):
    """Shared model for GIF and GRE — the fields line up 1:1."""

    model_config = ConfigDict(extra="forbid")

    kind: str  # "gif" | "gre"
    name: str  # gifif / greif value
    if_: str | None = None  # outer interface
    remote_addr: str | None = None
    tunnel_local_addr: str | None = None
    tunnel_remote_addr: str | None = None
    tunnel_remote_net: str | None = None
    descr: str | None = None


class Ppp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Stable key: the synthesized interface device name.
    ptpid: str
    type: str | None = None  # "ppp" | "pppoe" | "l2tp" | "pptp"
    if_: str | None = None  # underlying physical interface
    username: str | None = None
    # Password is always redacted downstream via field-name match; we
    # don't need a separate field here because ``<password>`` lives
    # inside ``<ppp>`` and the redaction engine catches it.
    provider: str | None = None
    phone: str | None = None
    descr: str | None = None


class QinQ(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Stable key: parent interface + tag pair.
    key: str
    if_: str | None = None
    tag: str | None = None
    members: list[str] = []
    descr: str | None = None


class WolHost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Stable key: MAC address.
    mac: str
    interface: str | None = None
    descr: str | None = None


class Lagg(BaseModel):
    """LAGG (link aggregation) interface — LACP or failover bond."""

    model_config = ConfigDict(extra="forbid")

    # Stable key: the synthesized laggN device.
    laggif: str
    members: list[str] = []
    proto: str | None = None  # lacp | failover | loadbalance | roundrobin | none
    lacptimeout: str | None = None
    lacp_fast_timeout: bool = False
    descr: str | None = None


def parse_vlans(root: Element) -> list[Vlan]:
    el = root.find("vlans")
    if el is None:
        return []
    out: list[Vlan] = []
    for v in children(el, "vlan"):
        iface = text(v, "if")
        tag = text(v, "tag")
        out.append(
            Vlan(
                key=f"{iface or '?'}.{tag or '?'}",
                if_=iface,
                tag=tag,
                pcp=text(v, "pcp"),
                vlanif=text(v, "vlanif"),
                descr=text(v, "descr"),
            )
        )
    return out


def parse_bridges(root: Element) -> list[Bridge]:
    el = root.find("bridges")
    if el is None:
        return []
    out: list[Bridge] = []
    for b in children(el, "bridged"):
        name = text(b, "bridgeif")
        if not name:
            continue
        members_raw = text(b, "members") or ""
        out.append(
            Bridge(
                bridgeif=name,
                members=members_raw.split(",") if members_raw else [],
                descr=text(b, "descr"),
                enablestp=bool_flag(b, "enablestp"),
            )
        )
    return out


def _parse_tunnels(root: Element, container: str, item: str, kind: str) -> list[Tunnel]:
    el = root.find(container)
    if el is None:
        return []
    out: list[Tunnel] = []
    for t in children(el, item):
        name = text(t, f"{kind}if") or text(t, "name")
        if not name:
            continue
        out.append(
            Tunnel(
                kind=kind,
                name=name,
                if_=text(t, "if"),
                remote_addr=text(t, "remote-addr") or text(t, "remote_addr"),
                tunnel_local_addr=text(t, "tunnel-local-addr"),
                tunnel_remote_addr=text(t, "tunnel-remote-addr"),
                tunnel_remote_net=text(t, "tunnel-remote-net"),
                descr=text(t, "descr"),
            )
        )
    return out


def parse_gifs(root: Element) -> list[Tunnel]:
    return _parse_tunnels(root, "gifs", "gif", "gif")


def parse_gres(root: Element) -> list[Tunnel]:
    return _parse_tunnels(root, "gres", "gre", "gre")


def parse_ppps(root: Element) -> list[Ppp]:
    el = root.find("ppps")
    if el is None:
        return []
    out: list[Ppp] = []
    for p in children(el, "ppp"):
        ptpid = text(p, "ptpid")
        if not ptpid:
            continue
        out.append(
            Ppp(
                ptpid=ptpid,
                type=text(p, "type"),
                if_=text(p, "if") or text(p, "ports"),
                username=text(p, "username"),
                provider=text(p, "provider"),
                phone=text(p, "phone"),
                descr=text(p, "descr"),
            )
        )
    return out


def parse_qinqs(root: Element) -> list[QinQ]:
    el = root.find("qinqs")
    if el is None:
        return []
    out: list[QinQ] = []
    for q in children(el, "qinqentry"):
        iface = text(q, "if")
        tag = text(q, "tag")
        members_raw = text(q, "members") or ""
        out.append(
            QinQ(
                key=f"{iface or '?'}.{tag or '?'}",
                if_=iface,
                tag=tag,
                members=members_raw.split() if members_raw else [],
                descr=text(q, "descr"),
            )
        )
    return out


def parse_laggs(root: Element) -> list[Lagg]:
    el = root.find("laggs")
    if el is None:
        return []
    out: list[Lagg] = []
    for la in children(el, "lagg"):
        name = text(la, "laggif")
        if not name:
            continue
        members_raw = text(la, "members") or ""
        out.append(
            Lagg(
                laggif=name,
                members=members_raw.split(",") if members_raw else [],
                proto=text(la, "proto"),
                lacptimeout=text(la, "lacptimeout"),
                lacp_fast_timeout=bool_flag(la, "lacp_fast_timeout"),
                descr=text(la, "descr"),
            )
        )
    return out


def parse_wol(root: Element) -> list[WolHost]:
    el = root.find("wol")
    if el is None:
        return []
    out: list[WolHost] = []
    for w in children(el, "wolentry"):
        mac = text(w, "mac")
        if not mac:
            continue
        out.append(
            WolHost(
                mac=mac,
                interface=text(w, "interface"),
                descr=text(w, "descr"),
            )
        )
    return out
