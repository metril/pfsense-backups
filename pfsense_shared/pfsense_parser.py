"""Parse a pfSense ``config.xml`` into a structured, redaction-aware model.

Public API: ``parse(xml_bytes) -> ParsedConfig``.

The parser is deliberately tolerant. Missing sections are ``None`` or
``[]``; unknown top-level tags are reported under
``unrecognized_sections`` so the UI can show them with a raw-XML
fallback disclosure. A raw-XML fallback payload is emitted per
unrecognized tag so the frontend doesn't need to re-parse the source.

Known-noisy sections (``widgets``, ``rrd``, ``pkgs``) are suppressed
entirely — they are expected to vary between backups and carry no
review value.
"""

from __future__ import annotations

from typing import Final
from xml.etree.ElementTree import Element, ParseError, tostring

from defusedxml.ElementTree import fromstring as _defused_fromstring
from pydantic import BaseModel, ConfigDict

from .pfsense_sections import (
    aliases as _aliases,
)
from .pfsense_sections import (
    apikeys as _apikeys,
)
from .pfsense_sections import (
    auth as _auth,
)
from .pfsense_sections import (
    cron as _cron,
)
from .pfsense_sections import (
    dyndns as _dyndns,
)
from .pfsense_sections import (
    extra_vpn as _extra_vpn,
)
from .pfsense_sections import (
    firewall as _firewall,
)
from .pfsense_sections import (
    ha as _ha,
)
from .pfsense_sections import (
    interfaces as _interfaces,
)
from .pfsense_sections import (
    layer2 as _layer2,
)
from .pfsense_sections import (
    misc as _misc,
)
from .pfsense_sections import (
    nat as _nat,
)
from .pfsense_sections import (
    notifications as _notifications,
)
from .pfsense_sections import (
    packages as _packages,
)
from .pfsense_sections import (
    pki as _pki,
)
from .pfsense_sections import (
    revision as _revision,
)
from .pfsense_sections import (
    routing as _routing,
)
from .pfsense_sections import (
    services as _services,
)
from .pfsense_sections import (
    services_extra as _services_extra,
)
from .pfsense_sections import (
    ssh as _ssh,
)
from .pfsense_sections import (
    sysctl as _sysctl,
)
from .pfsense_sections import (
    system as _system,
)
from .pfsense_sections import (
    vpn as _vpn,
)
from .pfsense_sections.aliases import Alias
from .pfsense_sections.apikeys import ApiKeyEntry
from .pfsense_sections.auth import AuthServer, Group, User
from .pfsense_sections.cron import CronJob
from .pfsense_sections.dyndns import DyndnsEntry
from .pfsense_sections.extra_vpn import L2tpConfig, PppoeServerEntry
from .pfsense_sections.firewall import FirewallRule
from .pfsense_sections.ha import HaSync, VirtualIP
from .pfsense_sections.interfaces import Interface
from .pfsense_sections.layer2 import Bridge, Lagg, Ppp, QinQ, Tunnel, Vlan, WolHost
from .pfsense_sections.misc import (
    DhcpBackend,
    DiagPreferences,
    EzShaperConfig,
    InterfaceGroup,
    LastChange,
    LegacyBridge,
    OvpnServerWizard,
    ProxyArpEntry,
    ThemePreference,
)
from .pfsense_sections.nat import NatRule
from .pfsense_sections.notifications import NotificationConfig
from .pfsense_sections.packages import InstalledPackages
from .pfsense_sections.pki import (
    Certificate,
    CertificateAuthority,
    CertificateRevocationList,
)
from .pfsense_sections.revision import Revision
from .pfsense_sections.routing import Gateway, GatewayGroup, StaticRoute
from .pfsense_sections.services import DhcpServer, DnsConfig
from .pfsense_sections.services_extra import (
    CaptivePortalZone,
    DhcpRelayConfig,
    DnShaperPipe,
    FtpProxyConfig,
    IgmpProxyEntry,
    LoadBalancerPool,
    LoadBalancerVirtualServer,
    NtpdConfig,
    RadvdInterfaceConfig,
    Schedule,
    ShaperQueue,
    SnmpdConfig,
    SyslogConfig,
    UpsConfig,
    VoucherRoll,
)
from .pfsense_sections.ssh import SshData
from .pfsense_sections.sysctl import SysctlTunable
from .pfsense_sections.system import SystemInfo
from .pfsense_sections.vpn import (
    IpsecPhase1,
    IpsecPhase2,
    IpsecPskEntry,
    OpenVpnClient,
    OpenVpnCsc,
    OpenVpnServer,
)

# Top-level tags we consume (so the fallback only reports truly unknown
# sections, not ones we intentionally parse). Package configs (``installed
# packages``) are listed here for v0.11.0 — their per-package parsers
# land in v0.11.4, but we don't want them polluting the unrecognized
# list until then; they'll be parsed in a later release.
_KNOWN: Final[frozenset[str]] = frozenset(
    {
        # v0.11.0 — parsed
        "version",  # surfaced on ParsedConfig.config_version
        "system",
        "revision",
        "sysctl",
        "cron",
        "interfaces",
        "gateways",
        "staticroutes",
        "filter",
        "nat",
        "aliases",
        "dhcpd",
        "dhcpdv6",
        "unbound",
        "dnsmasq",
        # v0.11.1 — L2 / routing extras
        "vlans",
        "bridges",
        "gifs",
        "gres",
        "ppps",
        "qinqs",
        "wol",
        "virtualip",
        "hasync",
        # v0.11.2 — services
        "ntpd",
        "snmpd",
        "syslog",
        "captiveportal",
        "schedules",
        "shaper",
        "dnshaper",
        "load_balancer",
        "dhcrelay",
        "dhcrelay6",
        # v0.11.4 — VPN / crypto
        "openvpn",
        "ipsec",
        "ca",
        "cert",
        "crl",
        # v0.11.5 — packages
        "installedpackages",
        # v0.12.0 — broader coverage
        "dyndnses",
        "laggs",
        "notifications",
        "igmpproxy",
        "radvd",
        "ups",
        "voucher",
        "ftpproxy",
        # v0.14.0 — remaining tags operators still saw in "Other sections"
        "sshdata",
        "lastchange",
        "theme",
        "diag",
        "dhcpbackend",
        "bridge",  # singular legacy
        "proxyarp",
        "ifgroups",
        "ezshaper",
        "ovpnserver",
        "apikeys",
        "l2tp",
        "pppoes",
    }
)


# Tags we deliberately ignore: noisy, binary, or redundant. These do not
# appear in ``unrecognized_sections``.
_IGNORED: Final[frozenset[str]] = frozenset({"widgets", "rrd", "pkgs"})


class PfSenseParseError(ValueError):
    """Raised when ``parse`` cannot extract a usable tree from the
    input bytes — malformed XML, truncation, or a root element that
    isn't ``<pfsense>``. Callers should translate this to a 422 /
    client-visible "this backup can't be parsed" rather than leaking
    the underlying stdlib ``ParseError`` traceback as a 500."""


class RawSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag: str
    xml: str  # pretty-printed fallback XML (UTF-8 string)


class ParsedConfig(BaseModel):
    """Structured, redaction-aware projection of a pfSense config.xml."""

    model_config = ConfigDict(extra="forbid")

    # ``<version>`` in config.xml — pfSense config-schema version, not the
    # pfSense software version. Useful as a header on the structured view.
    config_version: str | None = None
    system: SystemInfo | None = None
    revision: Revision | None = None
    sysctl: list[SysctlTunable] = []
    cron: list[CronJob] = []
    interfaces: list[Interface] = []
    vlans: list[Vlan] = []
    bridges: list[Bridge] = []
    gifs: list[Tunnel] = []
    gres: list[Tunnel] = []
    ppps: list[Ppp] = []
    qinqs: list[QinQ] = []
    laggs: list[Lagg] = []
    wol: list[WolHost] = []
    gateways: list[Gateway] = []
    gateway_groups: list[GatewayGroup] = []
    static_routes: list[StaticRoute] = []
    virtual_ips: list[VirtualIP] = []
    hasync: HaSync | None = None
    firewall_rules: list[FirewallRule] = []
    nat_rules: list[NatRule] = []
    aliases: list[Alias] = []
    dyndns_entries: list[DyndnsEntry] = []
    notifications: NotificationConfig | None = None
    dhcp_servers: list[DhcpServer] = []
    dhcp_relays: list[DhcpRelayConfig] = []
    dns: DnsConfig | None = None
    ntpd: NtpdConfig | None = None
    snmpd: SnmpdConfig | None = None
    syslog: SyslogConfig | None = None
    schedules: list[Schedule] = []
    shaper_queues: list[ShaperQueue] = []
    dnshaper_pipes: list[DnShaperPipe] = []
    lb_pools: list[LoadBalancerPool] = []
    lb_virtual_servers: list[LoadBalancerVirtualServer] = []
    captive_portal_zones: list[CaptivePortalZone] = []
    igmpproxy_entries: list[IgmpProxyEntry] = []
    radvd_interfaces: list[RadvdInterfaceConfig] = []
    ups: UpsConfig | None = None
    voucher_rolls: list[VoucherRoll] = []
    ftpproxy: FtpProxyConfig | None = None
    users: list[User] = []
    groups: list[Group] = []
    authservers: list[AuthServer] = []

    openvpn_servers: list[OpenVpnServer] = []
    openvpn_clients: list[OpenVpnClient] = []
    openvpn_cscs: list[OpenVpnCsc] = []
    ipsec_phase1: list[IpsecPhase1] = []
    ipsec_phase2: list[IpsecPhase2] = []
    ipsec_psks: list[IpsecPskEntry] = []
    certificate_authorities: list[CertificateAuthority] = []
    certificates: list[Certificate] = []
    crls: list[CertificateRevocationList] = []

    # v0.14.0 — tags operators still saw surfaced in the raw-XML panel.
    sshdata: SshData | None = None
    lastchange: LastChange | None = None
    theme: ThemePreference | None = None
    diag: DiagPreferences | None = None
    dhcp_backend: DhcpBackend | None = None
    legacy_bridge: LegacyBridge | None = None
    proxyarp: list[ProxyArpEntry] = []
    interface_groups: list[InterfaceGroup] = []
    ezshaper: EzShaperConfig | None = None
    ovpnserver_wizard: OvpnServerWizard | None = None
    apikeys: list[ApiKeyEntry] = []
    l2tp: L2tpConfig | None = None
    pppoe_servers: list[PppoeServerEntry] = []

    # Parsed <installedpackages> — known packages structured; unknown
    # packages carried in ``installedpackages.unknown`` with raw XML.
    installedpackages: InstalledPackages | None = None

    # Everything we didn't parse (outside the ignore list). Carries the
    # tag name and a serialized XML subtree so the UI can surface it.
    unrecognized_sections: list[RawSection] = []


def parse(xml_bytes: bytes | str) -> ParsedConfig:
    """Parse a decrypted pfSense ``config.xml`` into a model.

    Accepts either bytes (from the encrypted path via
    ``decrypt_pfsense_backup``) or str (from ``read_content`` which
    already decodes UTF-8 for plain backups). Empty / no-root edge
    cases surface as an empty ParsedConfig rather than raising.
    """
    if not xml_bytes or not (
        xml_bytes.strip() if isinstance(xml_bytes, str) else xml_bytes.strip()
    ):
        return ParsedConfig()

    try:
        root = _defused_fromstring(xml_bytes)
    except ParseError as exc:
        # defusedxml re-raises stdlib ParseError for malformed XML.
        # Without this wrap the traceback surfaces as an unhandled 500
        # on every downstream endpoint (``/parsed``, ``/diff/pair/parsed``,
        # ``/anchor-history``) — callers now catch ``PfSenseParseError``
        # and translate to a 422 with an actionable message.
        raise PfSenseParseError(f"backup content is not valid XML: {exc}") from exc
    # pfSense wraps everything in ``<pfsense>``; defusedxml gives us that
    # element as the root.
    gws, ggroups = _routing.parse_gateways(root)
    lb_pools, lb_vservers = _services_extra.parse_load_balancer(root)
    ovpn_servers, ovpn_clients, ovpn_cscs = _vpn.parse_openvpn(root)
    ipsec_p1, ipsec_p2, ipsec_psks = _vpn.parse_ipsec(root)
    ver_el = root.find("version")
    result = ParsedConfig(
        config_version=(ver_el.text or None) if ver_el is not None else None,
        system=_system.parse(root),
        revision=_revision.parse(root),
        sysctl=_sysctl.parse(root),
        cron=_cron.parse(root),
        interfaces=_interfaces.parse(root),
        vlans=_layer2.parse_vlans(root),
        bridges=_layer2.parse_bridges(root),
        gifs=_layer2.parse_gifs(root),
        gres=_layer2.parse_gres(root),
        ppps=_layer2.parse_ppps(root),
        qinqs=_layer2.parse_qinqs(root),
        laggs=_layer2.parse_laggs(root),
        wol=_layer2.parse_wol(root),
        gateways=gws,
        gateway_groups=ggroups,
        static_routes=_routing.parse_static_routes(root),
        virtual_ips=_ha.parse_virtualips(root),
        hasync=_ha.parse_hasync(root),
        firewall_rules=_firewall.parse(root),
        nat_rules=_nat.parse(root),
        aliases=_aliases.parse(root),
        dyndns_entries=_dyndns.parse(root),
        notifications=_notifications.parse(root),
        dhcp_servers=_services.parse_dhcp(root),
        dhcp_relays=_services_extra.parse_dhcp_relay(root),
        dns=_services.parse_dns(root),
        ntpd=_services_extra.parse_ntpd(root),
        snmpd=_services_extra.parse_snmpd(root),
        syslog=_services_extra.parse_syslog(root),
        schedules=_services_extra.parse_schedules(root),
        shaper_queues=_services_extra.parse_shaper(root),
        dnshaper_pipes=_services_extra.parse_dnshaper(root),
        lb_pools=lb_pools,
        lb_virtual_servers=lb_vservers,
        captive_portal_zones=_services_extra.parse_captive_portal(root),
        igmpproxy_entries=_services_extra.parse_igmpproxy(root),
        radvd_interfaces=_services_extra.parse_radvd(root),
        ups=_services_extra.parse_ups(root),
        voucher_rolls=_services_extra.parse_vouchers(root),
        ftpproxy=_services_extra.parse_ftpproxy(root),
        openvpn_servers=ovpn_servers,
        openvpn_clients=ovpn_clients,
        openvpn_cscs=ovpn_cscs,
        ipsec_phase1=ipsec_p1,
        ipsec_phase2=ipsec_p2,
        ipsec_psks=ipsec_psks,
        certificate_authorities=_pki.parse_cas(root),
        certificates=_pki.parse_certs(root),
        crls=_pki.parse_crls(root),
        sshdata=_ssh.parse(root),
        lastchange=_misc.parse_lastchange(root),
        theme=_misc.parse_theme(root),
        diag=_misc.parse_diag(root),
        dhcp_backend=_misc.parse_dhcpbackend(root),
        legacy_bridge=_misc.parse_legacy_bridge(root),
        proxyarp=_misc.parse_proxyarp(root),
        interface_groups=_misc.parse_ifgroups(root),
        ezshaper=_misc.parse_ezshaper(root),
        ovpnserver_wizard=_misc.parse_ovpnserver(root),
        apikeys=_apikeys.parse(root),
        l2tp=_extra_vpn.parse_l2tp(root),
        pppoe_servers=_extra_vpn.parse_pppoes(root),
        installedpackages=_packages.parse(root),
        users=_auth.parse_users(root),
        groups=_auth.parse_groups(root),
        authservers=_auth.parse_authservers(root),
        unrecognized_sections=_unrecognized(root),
    )
    return result


def _unrecognized(root: Element) -> list[RawSection]:
    out: list[RawSection] = []
    seen: set[str] = set()
    for child in list(root):
        tag = child.tag
        if tag in _KNOWN or tag in _IGNORED or tag in seen:
            continue
        seen.add(tag)
        # tostring returns bytes; UI wants a str.
        xml = tostring(child, encoding="unicode")
        out.append(RawSection(tag=tag, xml=xml))
    return out
