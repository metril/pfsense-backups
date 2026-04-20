"""Services that aren't DHCP/DNS: NTP, SNMP, syslog, captive portal,
schedules, shaper, dnshaper, load balancer, DHCP relay.

Secrets handled: SNMP community strings, captive-portal RADIUS shared
secrets, dnshaper / shaper have no secrets to speak of.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact

from ._helpers import bool_flag, children, text

# ---------- parsers -------------------------------------------------------
# (section models + legacy service parsers above; niche services at bottom)


class NtpdConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enable: bool = False
    interfaces: list[str] = []
    timeservers: list[str] = []
    orphan: str | None = None
    leapsec: str | None = None
    # Optional per-server flags are captured as raw server strings; the
    # diff sees a list of strings which is fine for change review.


class SnmpdConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enable: bool = False
    syslocation: str | None = None
    syscontact: str | None = None
    rocommunity: str | None = None  # redacted
    rwcommunity: str | None = None  # redacted
    pollport: str | None = None
    # Trap targets
    trapenable: bool = False
    trapserver: str | None = None
    trapserverport: str | None = None
    trapstring: str | None = None
    # Module toggles pfSense exposes in the UI
    bindlan: bool = False
    bindip: str | None = None


class SyslogHost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Stable key: host:port combo.
    key: str
    host: str
    sourceip: str | None = None
    ipprotocol: str | None = None


class SyslogConfig(BaseModel):
    """Global remote-syslog config plus the list of destinations."""

    model_config = ConfigDict(extra="forbid")

    enable: bool = False
    reverse: bool = False
    nentries: str | None = None
    # Filter toggles — pfSense has many; we expose the common ones.
    filter_: bool = False
    dhcp: bool = False
    portalauth: bool = False
    vpn: bool = False
    dpinger: bool = False
    hostapd: bool = False
    system: bool = False
    resolver: bool = False
    ppp: bool = False
    routing: bool = False
    ntpd: bool = False
    hosts: list[SyslogHost] = []


class DhcpRelayConfig(BaseModel):
    """dhcrelay or dhcrelay6 top-level config."""

    model_config = ConfigDict(extra="forbid")

    kind: str  # "ipv4" | "ipv6"
    enable: bool = False
    interface: list[str] = []
    server: list[str] = []
    agentoption: bool = False


class Schedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    descr: str | None = None
    # pfSense stores time blocks under <timerange>. We keep the raw
    # time slots plus a condensed human label the UI can display.
    time_ranges: list[str] = []


class ShaperQueue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    interface: str | None = None
    priority: str | None = None
    bandwidth: str | None = None
    bandwidthtype: str | None = None
    descr: str | None = None


class DnShaperPipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    number: str | None = None
    bandwidth: str | None = None
    bandwidthtype: str | None = None
    descr: str | None = None


class LoadBalancerPoolMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ip: str | None = None
    port: str | None = None


class LoadBalancerPool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    descr: str | None = None
    behaviour: str | None = None  # "balance" | "failover"
    port: str | None = None
    monitor: str | None = None
    servers: list[LoadBalancerPoolMember] = []


class LoadBalancerVirtualServer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    descr: str | None = None
    ipaddr: str | None = None
    port: str | None = None
    mode: str | None = None
    poolname: str | None = None


class CaptivePortalZone(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone: str
    zoneid: str | None = None
    enable: bool = False
    interfaces: list[str] = []
    auth_method: str | None = None  # "none" | "local" | "radius"
    redirurl: str | None = None
    # RADIUS secret is always redacted.
    radius_secret: str | None = None


class IgmpProxyEntry(BaseModel):
    """One ``<igmpproxy><item>`` — either an ``upstream`` or ``downstream`` side."""

    model_config = ConfigDict(extra="forbid")

    # Stable key: ``type|ifname`` (only one upstream is legal but downstream
    # entries are scoped per-interface, so the pair is unique).
    key: str
    type: str | None = None  # "upstream" | "downstream"
    ifname: str | None = None
    descr: str | None = None
    threshold: str | None = None
    # Scope filter entries (CIDR list) — pfSense stores them comma-separated.
    networks: list[str] = []


class RadvdInterfaceConfig(BaseModel):
    """pfSense's ``<radvd>`` has one block per interface. Each carries
    the advertised-prefix / managed-flag set that determines IPv6 SLAAC
    behaviour for that link."""

    model_config = ConfigDict(extra="forbid")

    # Stable key: interface name (lan, opt1, …). pfSense stores each
    # interface as a direct child element whose tag IS the interface.
    interface: str
    ramode: str | None = None  # "disabled" | "router" | "unmanaged" | ...
    rapriority: str | None = None
    ramininterval: str | None = None
    ramaxinterval: str | None = None
    ralifetime: str | None = None
    radomainsearchlist: str | None = None
    radns: list[str] = []


class UpsConfig(BaseModel):
    """NUT / apcupsd style UPS config. Uncommon in SMB, common in DC."""

    model_config = ConfigDict(extra="forbid")

    enable: bool = False
    driver: str | None = None  # apcsmart, usbhid-ups, etc.
    port: str | None = None
    cable: str | None = None
    upsname: str | None = None
    # Credentials for a remote NUT monitor — redacted.
    remoteuser: str | None = None
    remotepassword: str | None = None


class VoucherRoll(BaseModel):
    """Captive-portal voucher roll (batch of time-limited pre-generated codes)."""

    model_config = ConfigDict(extra="forbid")

    # Stable key: the roll id.
    number: str
    minutes: str | None = None  # minutes of access per code
    count: str | None = None  # codes remaining in this roll
    descr: str | None = None


class FtpProxyConfig(BaseModel):
    """Legacy FTP ALG / helper config. Mostly historical."""

    model_config = ConfigDict(extra="forbid")

    enable: bool = False
    ports: str | None = None
    interface: str | None = None


# ---------- parsers -------------------------------------------------------


def parse_ntpd(root: Element) -> NtpdConfig | None:
    el = root.find("ntpd")
    if el is None:
        return None
    ifaces_raw = text(el, "interface") or ""
    ts_raw = text(el, "timeservers") or ""
    # Also merge top-level <system><timeservers> — pfSense sets one or the
    # other depending on version — but we don't duplicate here; system's
    # parser already handles the global timeservers. The ntpd section is
    # about *ntpd's view* of time sources.
    return NtpdConfig(
        enable=bool_flag(el, "enable") or el.find("enable") is not None,
        interfaces=ifaces_raw.split(",") if ifaces_raw else [],
        timeservers=ts_raw.split() if ts_raw else [],
        orphan=text(el, "orphan"),
        leapsec=text(el, "leapsec"),
    )


def parse_snmpd(root: Element) -> SnmpdConfig | None:
    el = root.find("snmpd")
    if el is None:
        return None
    return SnmpdConfig(
        enable=bool_flag(el, "enable"),
        syslocation=text(el, "syslocation"),
        syscontact=text(el, "syscontact"),
        rocommunity=redact("rocommunity", text(el, "rocommunity")),
        rwcommunity=redact("rwcommunity", text(el, "rwcommunity")),
        pollport=text(el, "pollport"),
        trapenable=bool_flag(el, "trapenable"),
        trapserver=text(el, "trapserver"),
        trapserverport=text(el, "trapserverport"),
        trapstring=text(el, "trapstring"),
        bindlan=bool_flag(el, "bindlan"),
        bindip=text(el, "bindip"),
    )


def parse_syslog(root: Element) -> SyslogConfig | None:
    el = root.find("syslog")
    if el is None:
        return None
    hosts: list[SyslogHost] = []
    # pfSense supports up to 3 remote destinations; they're stored as
    # <remoteserver>, <remoteserver2>, <remoteserver3>.
    for tag in ("remoteserver", "remoteserver2", "remoteserver3"):
        val = text(el, tag)
        if val:
            hosts.append(SyslogHost(key=f"{tag}:{val}", host=val))
    return SyslogConfig(
        enable=bool_flag(el, "enable"),
        reverse=bool_flag(el, "reverse"),
        nentries=text(el, "nentries"),
        filter_=bool_flag(el, "filter"),
        dhcp=bool_flag(el, "dhcp"),
        portalauth=bool_flag(el, "portalauth"),
        vpn=bool_flag(el, "vpn"),
        dpinger=bool_flag(el, "dpinger"),
        hostapd=bool_flag(el, "hostapd"),
        system=bool_flag(el, "system"),
        resolver=bool_flag(el, "resolver"),
        ppp=bool_flag(el, "ppp"),
        routing=bool_flag(el, "routing"),
        ntpd=bool_flag(el, "ntpd"),
        hosts=hosts,
    )


def parse_dhcp_relay(root: Element) -> list[DhcpRelayConfig]:
    out: list[DhcpRelayConfig] = []
    for tag, kind in (("dhcrelay", "ipv4"), ("dhcrelay6", "ipv6")):
        el = root.find(tag)
        if el is None:
            continue
        iface_raw = text(el, "interface") or ""
        server_raw = text(el, "server") or ""
        out.append(
            DhcpRelayConfig(
                kind=kind,
                enable=bool_flag(el, "enable"),
                interface=iface_raw.split(",") if iface_raw else [],
                server=server_raw.split(",") if server_raw else [],
                agentoption=bool_flag(el, "agentoption"),
            )
        )
    return out


def parse_schedules(root: Element) -> list[Schedule]:
    el = root.find("schedules")
    if el is None:
        return []
    out: list[Schedule] = []
    for s in children(el, "schedule"):
        name = text(s, "name")
        if not name:
            continue
        ranges: list[str] = []
        for tr in children(s, "timerange"):
            parts = [
                f"M{text(tr, 'month') or '*'}D{text(tr, 'day') or '*'}",
                f"{text(tr, 'hour') or '*'}",
                f"range-descr:{text(tr, 'rangedescr') or ''}",
            ]
            ranges.append(" ".join(p for p in parts if p))
        out.append(
            Schedule(
                name=name,
                descr=text(s, "descr"),
                time_ranges=ranges,
            )
        )
    return out


def parse_shaper(root: Element) -> list[ShaperQueue]:
    el = root.find("shaper")
    if el is None:
        return []
    out: list[ShaperQueue] = []
    # pfSense shaper nests queues under <queue> with multiple levels;
    # we flatten and collect all leaf queues.

    def walk(node: Element) -> None:
        for q in children(node, "queue"):
            name = text(q, "name")
            if name:
                out.append(
                    ShaperQueue(
                        name=name,
                        interface=text(q, "interface"),
                        priority=text(q, "priority"),
                        bandwidth=text(q, "bandwidth"),
                        bandwidthtype=text(q, "bandwidthtype"),
                        descr=text(q, "descr"),
                    )
                )
            walk(q)

    walk(el)
    return out


def parse_dnshaper(root: Element) -> list[DnShaperPipe]:
    el = root.find("dnshaper")
    if el is None:
        return []
    out: list[DnShaperPipe] = []
    for p in children(el, "pipe"):
        name = text(p, "name")
        if not name:
            continue
        out.append(
            DnShaperPipe(
                name=name,
                number=text(p, "number"),
                bandwidth=text(p, "bandwidth"),
                bandwidthtype=text(p, "bandwidthtype"),
                descr=text(p, "descr"),
            )
        )
    return out


def parse_load_balancer(
    root: Element,
) -> tuple[list[LoadBalancerPool], list[LoadBalancerVirtualServer]]:
    el = root.find("load_balancer")
    if el is None:
        return [], []
    pools: list[LoadBalancerPool] = []
    for p in children(el, "lbpool"):
        name = text(p, "name")
        if not name:
            continue
        servers: list[LoadBalancerPoolMember] = []
        servers_raw = text(p, "servers") or ""
        for entry in servers_raw.split():
            if "|" in entry:
                ip, port = entry.split("|", 1)
                servers.append(LoadBalancerPoolMember(ip=ip, port=port))
            else:
                servers.append(LoadBalancerPoolMember(ip=entry))
        pools.append(
            LoadBalancerPool(
                name=name,
                descr=text(p, "descr"),
                behaviour=text(p, "behaviour"),
                port=text(p, "port"),
                monitor=text(p, "monitor"),
                servers=servers,
            )
        )
    vservers: list[LoadBalancerVirtualServer] = []
    for v in children(el, "virtual_server"):
        name = text(v, "name")
        if not name:
            continue
        vservers.append(
            LoadBalancerVirtualServer(
                name=name,
                descr=text(v, "descr"),
                ipaddr=text(v, "ipaddr"),
                port=text(v, "port"),
                mode=text(v, "mode"),
                poolname=text(v, "poolname"),
            )
        )
    return pools, vservers


def parse_captive_portal(root: Element) -> list[CaptivePortalZone]:
    el = root.find("captiveportal")
    if el is None:
        return []
    out: list[CaptivePortalZone] = []
    for z in list(el):
        # Each direct child is a zone keyed by tag name.
        name = z.tag
        ifaces_raw = text(z, "interface") or ""
        out.append(
            CaptivePortalZone(
                zone=name,
                zoneid=text(z, "zoneid"),
                enable=bool_flag(z, "enable"),
                interfaces=ifaces_raw.split(",") if ifaces_raw else [],
                auth_method=text(z, "auth_method"),
                redirurl=text(z, "redirurl"),
                radius_secret=redact("radius_secret", text(z, "radius_secret")),
            )
        )
    return out


def parse_igmpproxy(root: Element) -> list[IgmpProxyEntry]:
    el = root.find("igmpproxy")
    if el is None:
        return []
    out: list[IgmpProxyEntry] = []
    for item in children(el, "item"):
        typ = text(item, "type")
        ifname = text(item, "ifname")
        networks_raw = text(item, "network") or text(item, "networks") or ""
        out.append(
            IgmpProxyEntry(
                key=f"{typ or '?'}|{ifname or '?'}",
                type=typ,
                ifname=ifname,
                descr=text(item, "descr"),
                threshold=text(item, "threshold"),
                networks=[n.strip() for n in networks_raw.split(",") if n.strip()],
            )
        )
    return out


def parse_radvd(root: Element) -> list[RadvdInterfaceConfig]:
    el = root.find("radvd")
    if el is None:
        return []
    out: list[RadvdInterfaceConfig] = []
    for iface in list(el):
        dns_raw = text(iface, "radns") or ""
        out.append(
            RadvdInterfaceConfig(
                interface=iface.tag,
                ramode=text(iface, "ramode"),
                rapriority=text(iface, "rapriority"),
                ramininterval=text(iface, "ramininterval"),
                ramaxinterval=text(iface, "ramaxinterval"),
                ralifetime=text(iface, "ralifetime"),
                radomainsearchlist=text(iface, "radomainsearchlist"),
                radns=[s.strip() for s in dns_raw.split() if s.strip()],
            )
        )
    return out


def parse_ups(root: Element) -> UpsConfig | None:
    el = root.find("ups")
    if el is None:
        return None
    return UpsConfig(
        enable=bool_flag(el, "enable"),
        driver=text(el, "driver"),
        port=text(el, "port"),
        cable=text(el, "cable"),
        upsname=text(el, "upsname"),
        remoteuser=text(el, "remoteuser"),
        remotepassword=redact("password", text(el, "remotepassword")),
    )


def parse_vouchers(root: Element) -> list[VoucherRoll]:
    el = root.find("voucher")
    if el is None:
        return []
    out: list[VoucherRoll] = []
    for roll in children(el, "roll"):
        num = text(roll, "number")
        if not num:
            continue
        out.append(
            VoucherRoll(
                number=num,
                minutes=text(roll, "minutes"),
                count=text(roll, "count"),
                descr=text(roll, "descr"),
            )
        )
    return out


def parse_ftpproxy(root: Element) -> FtpProxyConfig | None:
    el = root.find("ftpproxy")
    if el is None:
        return None
    return FtpProxyConfig(
        enable=bool_flag(el, "enable"),
        ports=text(el, "ports"),
        interface=text(el, "interface"),
    )
