"""Parses FRR (Free Range Routing) package config under
``<installedpackages>``.

The pfSense FRR package exposes OSPF and BGP daemons. Config shapes
vary by version — we capture the common surface: daemon enables,
router IDs, BGP peers, OSPF areas + interfaces. BGP / OSPF auth
passwords (MD5 keys) are redacted.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact
from pfsense_shared.pfsense_sections._helpers import bool_flag, children, text


class FrrBgpNeighbor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str  # peer-group / neighbor name
    remote_as: str | None = None
    peer_address: str | None = None
    descr: str | None = None
    # Redacted — MD5 password / TCP-AO key
    password: str | None = None


class FrrBgpConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    local_as: str | None = None
    router_id: str | None = None
    neighbors: list[FrrBgpNeighbor] = []


class FrrOspfInterface(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interface: str
    area: str | None = None
    cost: str | None = None
    priority: str | None = None
    hello_interval: str | None = None
    dead_interval: str | None = None
    # Redacted when the interface uses MD5 auth
    md5_password: str | None = None


class FrrOspfConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    router_id: str | None = None
    interfaces: list[FrrOspfInterface] = []


class FrrOspfdInterface(BaseModel):
    """Single row of ``<frrospfdinterfaces>`` — OSPFv3 (IPv6) per-
    interface configuration. Mirrors ``FrrOspfInterface`` for IPv4;
    any MD5 / BGP-AO key fields are redacted via the existing
    ``ospf_password`` redaction tag."""

    model_config = ConfigDict(extra="forbid")

    interface: str
    area: str | None = None
    cost: str | None = None
    priority: str | None = None
    hello_interval: str | None = None
    dead_interval: str | None = None
    # Redacted when the interface uses MD5 auth (rare for OSPFv3 —
    # IPsec AH is more typical — but some builds surface a key here).
    md5_password: str | None = None


class FrrConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    bgp: FrrBgpConfig | None = None
    ospf: FrrOspfConfig | None = None
    # v0.16.0: FRR's OSPFd (IPv6 OSPF) daemon and a handful of shared
    # global policy tables live under separate top-level package tags.
    # We surface presence so operators see the daemon/policy is
    # configured without stranding the tags in "Other packages";
    # structural details stay available via the raw-XML fallback.
    ospfd_present: bool = False
    ospfd_areas_present: bool = False
    ospfd_interfaces_present: bool = False
    global_acls_present: bool = False
    global_prefixes_present: bool = False
    # v0.16.1: structured OSPFv3 interface rows so any MD5 auth keys
    # pass through the redaction engine instead of being silently
    # dropped. Empty list when no interface rows exist OR when the
    # tag is absent entirely.
    ospfd_interfaces: list[FrrOspfdInterface] = []


CONSUMED_TAGS = frozenset(
    {
        "frr",
        "frrbgp",
        "frrospf",
        "frrglobal",
        "frrbgpneighbors",
        "frrospfinterfaces",
        # v0.16.0 — IPv6 OSPF daemon + global policy tables.
        "frrospfd",
        "frrospfdareas",
        "frrospfdinterfaces",
        "frrglobalacls",
        "frrglobalprefixes",
    }
)


def _parse_bgp(ip: Element) -> FrrBgpConfig | None:
    bgp_el = ip.find("frrbgp")
    neighbors_el = ip.find("frrbgpneighbors")
    # frrglobal alone does NOT imply BGP is enabled — older FRR
    # builds keep the daemon config under a daemon-specific tag.
    # Falling back to frrglobal here would double-populate BGP + OSPF
    # from the same element when only a global block exists.
    if bgp_el is None and neighbors_el is None:
        return None
    neighbors: list[FrrBgpNeighbor] = []
    if neighbors_el is not None:
        neighbor_rows = children(neighbors_el, "item")
        if not neighbor_rows:
            neighbor_rows = children(neighbors_el, "config")
        for n in neighbor_rows:
            name = (
                text(n, "name")
                or text(n, "peergroupname")
                or text(n, "peer_address")
                or "?"
            )
            neighbors.append(
                FrrBgpNeighbor(
                    name=name,
                    remote_as=text(n, "remote_as") or text(n, "remoteas"),
                    peer_address=text(n, "peer_address") or text(n, "peeraddr"),
                    descr=text(n, "descr"),
                    password=redact(
                        "bgp_password",
                        text(n, "password")
                        or text(n, "md5password")
                        or text(n, "bgp_password"),
                    ),
                )
            )
    if bgp_el is None:
        return FrrBgpConfig(enabled=False, neighbors=neighbors)
    return FrrBgpConfig(
        enabled=bool_flag(bgp_el, "enable") or bool_flag(bgp_el, "enablebgp"),
        local_as=text(bgp_el, "local_as") or text(bgp_el, "asnum"),
        router_id=text(bgp_el, "router_id") or text(bgp_el, "routerid"),
        neighbors=neighbors,
    )


def _parse_ospf(ip: Element) -> FrrOspfConfig | None:
    ospf_el = ip.find("frrospf")
    ifaces_el = ip.find("frrospfinterfaces")
    # Same anti-fallback as BGP: frrglobal is neither.
    if ospf_el is None and ifaces_el is None:
        return None
    interfaces: list[FrrOspfInterface] = []
    if ifaces_el is not None:
        iface_rows = children(ifaces_el, "item")
        if not iface_rows:
            iface_rows = children(ifaces_el, "config")
        for i in iface_rows:
            iface = text(i, "interface") or text(i, "interfacename")
            if not iface:
                continue
            interfaces.append(
                FrrOspfInterface(
                    interface=iface,
                    area=text(i, "area"),
                    cost=text(i, "cost"),
                    priority=text(i, "priority"),
                    hello_interval=text(i, "hello_interval")
                    or text(i, "hellointerval"),
                    dead_interval=text(i, "dead_interval")
                    or text(i, "deadinterval"),
                    md5_password=redact(
                        "ospf_password",
                        text(i, "md5_password") or text(i, "md5password"),
                    ),
                )
            )
    if ospf_el is None:
        return FrrOspfConfig(enabled=False, interfaces=interfaces)
    return FrrOspfConfig(
        enabled=bool_flag(ospf_el, "enable") or bool_flag(ospf_el, "enableospf"),
        router_id=text(ospf_el, "router_id") or text(ospf_el, "routerid"),
        interfaces=interfaces,
    )


def _parse_ospfd_interfaces(
    ifaces_el: Element | None,
) -> list[FrrOspfdInterface]:
    """OSPFv3 per-interface rows. Same row shape as the OSPFv2
    parser; we pipe any MD5 key field through redact() defensively
    even though OSPFv3 typically uses IPsec AH instead."""
    if ifaces_el is None:
        return []
    out: list[FrrOspfdInterface] = []
    rows = children(ifaces_el, "item")
    if not rows:
        rows = children(ifaces_el, "config")
    for i in rows:
        iface = text(i, "interface") or text(i, "interfacename")
        if not iface:
            continue
        out.append(
            FrrOspfdInterface(
                interface=iface,
                area=text(i, "area"),
                cost=text(i, "cost"),
                priority=text(i, "priority"),
                hello_interval=text(i, "hello_interval")
                or text(i, "hellointerval"),
                dead_interval=text(i, "dead_interval")
                or text(i, "deadinterval"),
                md5_password=redact(
                    "ospf_password",
                    text(i, "md5_password")
                    or text(i, "md5password")
                    or text(i, "ospf6authkey"),
                ),
            )
        )
    return out


def parse(ip: Element) -> FrrConfig | None:
    global_el = ip.find("frr")
    if global_el is None:
        global_el = ip.find("frrglobal")
    bgp = _parse_bgp(ip)
    ospf = _parse_ospf(ip)
    ospfd = ip.find("frrospfd")
    ospfd_areas = ip.find("frrospfdareas")
    ospfd_ifaces_el = ip.find("frrospfdinterfaces")
    ospfd_ifaces = _parse_ospfd_interfaces(ospfd_ifaces_el)
    global_acls = ip.find("frrglobalacls")
    global_prefixes = ip.find("frrglobalprefixes")
    if all(
        x is None
        for x in (
            global_el,
            bgp,
            ospf,
            ospfd,
            ospfd_areas,
            ospfd_ifaces_el,
            global_acls,
            global_prefixes,
        )
    ):
        return None
    enabled = False
    if global_el is not None:
        enabled = bool_flag(global_el, "enable") or bool_flag(global_el, "enablefrr")
    return FrrConfig(
        enabled=enabled,
        bgp=bgp,
        ospf=ospf,
        ospfd_present=ospfd is not None,
        ospfd_areas_present=ospfd_areas is not None,
        ospfd_interfaces_present=ospfd_ifaces_el is not None,
        global_acls_present=global_acls is not None,
        global_prefixes_present=global_prefixes is not None,
        ospfd_interfaces=ospfd_ifaces,
    )
