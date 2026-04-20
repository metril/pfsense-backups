"""Parses the eight small top-level tags that v0.13.0 still left
under "Other sections (raw XML)" — the cosmetic / legacy / wizard
tags that show up in real pfSense backups but don't justify their
own file.

- ``<lastchange>``  — epoch timestamp of the last config save
- ``<theme>``       — webGUI theme preference
- ``<diag>``        — diagnostic-page UI preferences
- ``<dhcpbackend>`` — DHCP backend selector ("kea" vs "isc")
- ``<bridge>``      — singular legacy bridge tag (captured raw)
- ``<proxyarp>``    — Proxy-ARP entries
- ``<ifgroups>``    — named interface groups (firewall targets)
- ``<ezshaper>``    — Traffic Shaper wizard scratchpad
- ``<ovpnserver>``  — OpenVPN Server wizard scratchpad (may carry
                      partial CA / cert key material — redacted)
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact

from ._helpers import bool_flag, children, text


class LastChange(BaseModel):
    """Single scalar: epoch seconds of the last config save."""

    model_config = ConfigDict(extra="forbid")

    time: str | None = None
    username: str | None = None


def parse_lastchange(root: Element) -> LastChange | None:
    el = root.find("lastchange")
    if el is None:
        return None
    # pfSense emits either ``<lastchange>1234567890</lastchange>`` or
    # ``<lastchange><time>…</time><username>…</username></lastchange>``.
    # Handle both.
    if el.text and el.text.strip() and not list(el):
        return LastChange(time=el.text.strip())
    return LastChange(
        time=text(el, "time"),
        username=text(el, "username"),
    )


class ThemePreference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None


def parse_theme(root: Element) -> ThemePreference | None:
    el = root.find("theme")
    if el is None:
        return None
    if el.text and el.text.strip() and not list(el):
        return ThemePreference(name=el.text.strip())
    return ThemePreference(name=text(el, "name"))


class DiagPreferences(BaseModel):
    """Diagnostic-menu UI toggles. None of these are credentials —
    ``showallpasswords`` is a boolean preference, not a password."""

    model_config = ConfigDict(extra="forbid")

    ipv6nat: bool = False
    shownoaliases: bool = False
    showallpasswords: bool = False


def parse_diag(root: Element) -> DiagPreferences | None:
    el = root.find("diag")
    if el is None:
        return None
    return DiagPreferences(
        ipv6nat=bool_flag(el, "ipv6nat"),
        shownoaliases=bool_flag(el, "shownoaliases"),
        showallpasswords=bool_flag(el, "showallpasswords"),
    )


class DhcpBackend(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: str | None = None  # "kea" | "isc" | other


def parse_dhcpbackend(root: Element) -> DhcpBackend | None:
    el = root.find("dhcpbackend")
    if el is None:
        return None
    if el.text and el.text.strip() and not list(el):
        return DhcpBackend(backend=el.text.strip())
    return DhcpBackend(backend=text(el, "backend"))


class LegacyBridge(BaseModel):
    """Singular ``<bridge>`` tag — pfSense's legacy integrated bridging.
    Modern configs use ``<bridges><bridged>…</bridged></bridges>``; this
    is surfaced so it appears in the structured view alongside the
    modern bridges section with a "legacy format" label rather than
    falling into raw XML."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    interfaces: list[str] = []


def parse_legacy_bridge(root: Element) -> LegacyBridge | None:
    el = root.find("bridge")
    if el is None:
        return None
    ifs_raw = text(el, "interfaces") or ""
    return LegacyBridge(
        enabled=bool_flag(el, "enable"),
        interfaces=[i for i in ifs_raw.split(",") if i],
    )


class ProxyArpEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Stable diff key — network + interface combo.
    key: str
    interface: str | None = None
    network: str | None = None
    descr: str | None = None


def parse_proxyarp(root: Element) -> list[ProxyArpEntry]:
    el = root.find("proxyarp")
    if el is None:
        return []
    out: list[ProxyArpEntry] = []
    # pfSense wraps entries in ``<proxyarpnet>`` children.
    for n in children(el, "proxyarpnet"):
        iface = text(n, "interface")
        network = text(n, "network") or text(n, "address")
        out.append(
            ProxyArpEntry(
                key=f"{iface or '?'}|{network or '?'}",
                interface=iface,
                network=network,
                descr=text(n, "descr"),
            )
        )
    return out


class InterfaceGroup(BaseModel):
    """A named interface group — firewall rules can target these the
    same way they target individual interfaces. Surfacing them as a
    first-class xref target means rule reviews actually trace."""

    model_config = ConfigDict(extra="forbid")

    ifname: str
    members: list[str] = []
    descr: str | None = None


def parse_ifgroups(root: Element) -> list[InterfaceGroup]:
    el = root.find("ifgroups")
    if el is None:
        return []
    out: list[InterfaceGroup] = []
    # pfSense wraps each group in ``<ifgroupentry>``.
    for g in children(el, "ifgroupentry"):
        name = text(g, "ifname")
        if not name:
            continue
        members_raw = text(g, "members") or ""
        out.append(
            InterfaceGroup(
                ifname=name,
                members=[m for m in members_raw.split(" ") if m],
                descr=text(g, "descr"),
            )
        )
    return out


class EzShaperQueue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    bandwidth: str | None = None
    bandwidth_unit: str | None = None


class EzShaperConfig(BaseModel):
    """Traffic Shaper wizard scratchpad. The wizard stores its last
    completed-step state here so operators can re-open the wizard and
    edit rather than starting over. None of these carry secrets."""

    model_config = ConfigDict(extra="forbid")

    step: str | None = None
    interface: str | None = None
    upload: str | None = None
    download: str | None = None
    queues: list[EzShaperQueue] = []


def parse_ezshaper(root: Element) -> EzShaperConfig | None:
    el = root.find("ezshaper")
    if el is None:
        return None
    queues: list[EzShaperQueue] = []
    # Wizard state uses ``<step0>``/``<step1>``/… for each completed
    # step. Queue data typically nests under whichever step defined
    # it; rather than guessing the exact wrapper, walk any
    # ``<queue>`` descendant.
    for q in el.iter("queue"):
        name = text(q, "name")
        if not name:
            continue
        queues.append(
            EzShaperQueue(
                name=name,
                bandwidth=text(q, "bandwidth"),
                bandwidth_unit=text(q, "bandwidth_unit")
                or text(q, "bandwidthtype"),
            )
        )
    return EzShaperConfig(
        step=text(el, "step"),
        interface=text(el, "interface"),
        upload=text(el, "upload"),
        download=text(el, "download"),
        queues=queues,
    )


class OvpnServerWizard(BaseModel):
    """Scratchpad written by the OpenVPN Server wizard before the
    real ``<openvpn>`` entries land. May contain partial CA / cert
    material typed during the wizard — every ``*key`` value here
    routes through the redaction engine."""

    model_config = ConfigDict(extra="forbid")

    step: str | None = None
    description: str | None = None
    # Partial CA material
    cacrt: str | None = None
    cakey: str | None = None
    # Partial server cert material
    crt: str | None = None
    key: str | None = None


def parse_ovpnserver(root: Element) -> OvpnServerWizard | None:
    el = root.find("ovpnserver")
    if el is None:
        return None
    return OvpnServerWizard(
        step=text(el, "step"),
        description=text(el, "description") or text(el, "descr"),
        cacrt=text(el, "cacrt"),
        # ``<cakey>`` is the CA private half; reuse the ``prv`` tag name
        # from the core PKI parser so the same redaction entry covers
        # both sites.
        cakey=redact("prv", text(el, "cakey")),
        crt=text(el, "crt"),
        key=redact("prv", text(el, "key")),
    )
