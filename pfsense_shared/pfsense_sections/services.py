"""Parses DHCP servers, DNS resolver (unbound) and DNS forwarder (dnsmasq).

Other service sections (ntpd, snmpd, syslog, captive portal, dhcrelay,
shaper, …) land in the v0.11.1 / v0.11.2 phase.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact

from ._helpers import bool_flag, children, text


class DhcpStaticMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mac: str | None = None
    ipaddr: str | None = None
    hostname: str | None = None
    descr: str | None = None
    # v0.42.0 — per-mapping overrides. ``ddnsdomain`` makes this
    # mapping update a specific DDNS zone (rather than the
    # interface-wide one); ``filename`` + ``rootpath`` drive PXE /
    # BOOTP behaviour; ``gateway`` + ``dnsservers`` override the
    # interface defaults for this client.
    ddnsdomain: str | None = None
    filename: str | None = None
    rootpath: str | None = None
    gateway: str | None = None
    dnsservers: list[str] = []


class DhcpNumberOption(BaseModel):
    """One custom DHCP option override (``<numberoptions><item>``)."""

    model_config = ConfigDict(extra="forbid")

    number: str | None = None
    value: str | None = None
    type: str | None = None  # text | string | boolean | ...


class DhcpServer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Key: interface name (lan/opt1/...)
    interface: str
    enabled: bool = False
    range_from: str | None = None
    range_to: str | None = None
    domain: str | None = None
    # dnsserver repeats
    dnsservers: list[str] = []
    # gateway + domain_search
    gateway: str | None = None
    domainsearchlist: str | None = None
    static_mappings: list[DhcpStaticMap] = []
    # v0.42.0 — broader DHCP server-wide fields. Custom numberoptions
    # are vendor / option overrides (e.g. option 252 for WPAD); DDNS
    # block configures the interface-wide dynamic DNS update; lease
    # times tune how long leases last.
    numberoptions: list[DhcpNumberOption] = []
    ddnsdomain: str | None = None
    ddnsdomainprimary: str | None = None
    ddnsdomainkey: str | None = None  # redacted (TSIG key for DDNS nsupdate)
    defaultleasetime: str | None = None
    maxleasetime: str | None = None


class DnsHostAlias(BaseModel):
    """One alias under a DNS Resolver host override. pfSense lets each
    host override carry a list of additional ``host``+``domain``
    aliases that resolve to the same IP — historically silently
    dropped from the structured view."""

    model_config = ConfigDict(extra="forbid")

    host: str | None = None
    domain: str | None = None
    description: str | None = None


class DnsHostOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str | None = None
    domain: str | None = None
    ip: str | None = None
    descr: str | None = None
    aliases: list[DnsHostAlias] = []


class DnsDomainOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str | None = None
    ip: str | None = None
    descr: str | None = None


class DnsConfig(BaseModel):
    """Combined DNS info — unbound + dnsmasq both feed this."""

    model_config = ConfigDict(extra="forbid")

    # Which services are on.
    unbound_enabled: bool = False
    dnsmasq_enabled: bool = False
    unbound_port: str | None = None
    dnsmasq_port: str | None = None
    # Host + domain overrides unified across both services.
    host_overrides: list[DnsHostOverride] = []
    domain_overrides: list[DnsDomainOverride] = []


def parse_dhcp(root: Element) -> list[DhcpServer]:
    out: list[DhcpServer] = []
    for tag in ("dhcpd", "dhcpdv6"):
        el = root.find(tag)
        if el is None:
            continue
        for iface in list(el):
            # Each child tag is an interface name (lan, wan, opt1, ...).
            range_el = iface.find("range")
            dns_list = [
                e.text or ""
                for e in children(iface, "dnsserver")
                if (e.text or "").strip()
            ]
            maps: list[DhcpStaticMap] = []
            for sm in children(iface, "staticmap"):
                sm_dns = [
                    e.text or ""
                    for e in children(sm, "dnsserver")
                    if (e.text or "").strip()
                ]
                maps.append(
                    DhcpStaticMap(
                        mac=text(sm, "mac"),
                        ipaddr=text(sm, "ipaddr"),
                        hostname=text(sm, "hostname"),
                        descr=text(sm, "descr"),
                        ddnsdomain=text(sm, "ddnsdomain"),
                        filename=text(sm, "filename"),
                        rootpath=text(sm, "rootpath"),
                        gateway=text(sm, "gateway"),
                        dnsservers=sm_dns,
                    )
                )
            numopts: list[DhcpNumberOption] = []
            numopts_block = iface.find("numberoptions")
            if numopts_block is not None:
                for opt in children(numopts_block, "item"):
                    numopts.append(
                        DhcpNumberOption(
                            number=text(opt, "number"),
                            value=text(opt, "value"),
                            type=text(opt, "type"),
                        )
                    )
            out.append(
                DhcpServer(
                    interface=f"{iface.tag}" if tag == "dhcpd" else f"{iface.tag} (v6)",
                    enabled=bool_flag(iface, "enable"),
                    range_from=text(range_el, "from") if range_el is not None else None,
                    range_to=text(range_el, "to") if range_el is not None else None,
                    domain=text(iface, "domain"),
                    dnsservers=dns_list,
                    gateway=text(iface, "gateway"),
                    domainsearchlist=text(iface, "domainsearchlist"),
                    static_mappings=maps,
                    numberoptions=numopts,
                    ddnsdomain=text(iface, "ddnsdomain"),
                    ddnsdomainprimary=text(iface, "ddnsdomainprimary"),
                    ddnsdomainkey=redact("ddnsdomainkey", text(iface, "ddnsdomainkey")),
                    defaultleasetime=text(iface, "defaultleasetime"),
                    maxleasetime=text(iface, "maxleasetime"),
                )
            )
    return out


def _host_overrides(el: Element | None) -> list[DnsHostOverride]:
    if el is None:
        return []
    out: list[DnsHostOverride] = []
    for ho in children(el, "hosts"):
        aliases: list[DnsHostAlias] = []
        # ``<aliases>`` carries zero or more ``<item>`` children, each
        # an additional host+domain that resolves to the override's IP.
        # Previously silently dropped — fixed in v0.42.0.
        aliases_el = ho.find("aliases")
        if aliases_el is not None:
            for item in children(aliases_el, "item"):
                aliases.append(
                    DnsHostAlias(
                        host=text(item, "host"),
                        domain=text(item, "domain"),
                        description=text(item, "description"),
                    )
                )
        out.append(
            DnsHostOverride(
                host=text(ho, "host"),
                domain=text(ho, "domain"),
                ip=text(ho, "ip"),
                descr=text(ho, "descr"),
                aliases=aliases,
            )
        )
    return out


def _domain_overrides(el: Element | None) -> list[DnsDomainOverride]:
    if el is None:
        return []
    out: list[DnsDomainOverride] = []
    for do in children(el, "domainoverrides"):
        out.append(
            DnsDomainOverride(
                domain=text(do, "domain"),
                ip=text(do, "ip"),
                descr=text(do, "descr"),
            )
        )
    return out


def parse_dns(root: Element) -> DnsConfig | None:
    unbound_el = root.find("unbound")
    dnsmasq_el = root.find("dnsmasq")
    if unbound_el is None and dnsmasq_el is None:
        return None

    hosts: list[DnsHostOverride] = []
    domains: list[DnsDomainOverride] = []
    if unbound_el is not None:
        hosts.extend(_host_overrides(unbound_el))
        domains.extend(_domain_overrides(unbound_el))
    if dnsmasq_el is not None:
        hosts.extend(_host_overrides(dnsmasq_el))
        domains.extend(_domain_overrides(dnsmasq_el))

    return DnsConfig(
        unbound_enabled=bool_flag(unbound_el, "enable") if unbound_el is not None else False,
        dnsmasq_enabled=bool_flag(dnsmasq_el, "enable") if dnsmasq_el is not None else False,
        unbound_port=text(unbound_el, "port"),
        dnsmasq_port=text(dnsmasq_el, "port"),
        host_overrides=hosts,
        domain_overrides=domains,
    )
