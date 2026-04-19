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
from xml.etree.ElementTree import Element, tostring

from defusedxml.ElementTree import fromstring as _defused_fromstring
from pydantic import BaseModel, ConfigDict

from .pfsense_sections import (
    aliases as _aliases,
)
from .pfsense_sections import (
    auth as _auth,
)
from .pfsense_sections import (
    cron as _cron,
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
    nat as _nat,
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
    sysctl as _sysctl,
)
from .pfsense_sections import (
    system as _system,
)
from .pfsense_sections.aliases import Alias
from .pfsense_sections.auth import AuthServer, Group, User
from .pfsense_sections.cron import CronJob
from .pfsense_sections.firewall import FirewallRule
from .pfsense_sections.ha import HaSync, VirtualIP
from .pfsense_sections.interfaces import Interface
from .pfsense_sections.layer2 import Bridge, Ppp, QinQ, Tunnel, Vlan, WolHost
from .pfsense_sections.nat import NatRule
from .pfsense_sections.revision import Revision
from .pfsense_sections.routing import Gateway, GatewayGroup, StaticRoute
from .pfsense_sections.services import DhcpServer, DnsConfig
from .pfsense_sections.sysctl import SysctlTunable
from .pfsense_sections.system import SystemInfo

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
        # v0.11.1+ — known but not yet parsed; already-planned follow-ups
        "vlans",
        "bridges",
        "gifs",
        "gres",
        "ppps",
        "qinqs",
        "wol",
        "virtualip",
        "hasync",
        # v0.11.2+
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
        # v0.11.3+
        "openvpn",
        "ipsec",
        "ca",
        "cert",
        # v0.11.4+
        "installedpackages",
    }
)


# Tags we deliberately ignore: noisy, binary, or redundant. These do not
# appear in ``unrecognized_sections``.
_IGNORED: Final[frozenset[str]] = frozenset({"widgets", "rrd", "pkgs"})


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
    wol: list[WolHost] = []
    gateways: list[Gateway] = []
    gateway_groups: list[GatewayGroup] = []
    static_routes: list[StaticRoute] = []
    virtual_ips: list[VirtualIP] = []
    hasync: HaSync | None = None
    firewall_rules: list[FirewallRule] = []
    nat_rules: list[NatRule] = []
    aliases: list[Alias] = []
    dhcp_servers: list[DhcpServer] = []
    dns: DnsConfig | None = None
    users: list[User] = []
    groups: list[Group] = []
    authservers: list[AuthServer] = []

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

    root = _defused_fromstring(xml_bytes)
    # pfSense wraps everything in ``<pfsense>``; defusedxml gives us that
    # element as the root.
    gws, ggroups = _routing.parse_gateways(root)
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
        wol=_layer2.parse_wol(root),
        gateways=gws,
        gateway_groups=ggroups,
        static_routes=_routing.parse_static_routes(root),
        virtual_ips=_ha.parse_virtualips(root),
        hasync=_ha.parse_hasync(root),
        firewall_rules=_firewall.parse(root),
        nat_rules=_nat.parse(root),
        aliases=_aliases.parse(root),
        dhcp_servers=_services.parse_dhcp(root),
        dns=_services.parse_dns(root),
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
