"""Parses ``<interfaces>`` — WAN / LAN / OPTn logical interfaces.

Each direct child of ``<interfaces>`` is a logical interface keyed by its
pfSense-internal name (``wan``, ``lan``, ``opt1``, …). The physical
device lives in ``<if>``.

Excludes L2 sub-configs (VLANs, bridges, GIF/GRE/PPP) — those live
under their own top-level tags and get their own section parsers in
v0.11.1.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from ._helpers import bool_flag, text


class Interface(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Key: the element tag (wan/lan/opt1/...) is the stable matching key
    # across backups.
    key: str
    descr: str | None = None
    # Physical device (em0, igb0, vmx0.4094, ...)
    if_: str | None = None
    enabled: bool = False
    # IPv4 addressing — ``ipaddr`` is either an IP, "dhcp", "pppoe",
    # "ppp", "l2tp", or "pptp"; ``subnet`` is the mask bits.
    ipaddr: str | None = None
    subnet: str | None = None
    gateway: str | None = None
    # IPv6 — ``ipaddrv6`` parallels ``ipaddr`` with "track6", "dhcp6",
    # "6rd", "6to4", or a literal address.
    ipaddrv6: str | None = None
    subnetv6: str | None = None
    gatewayv6: str | None = None
    # Optional per-iface overrides.
    mtu: str | None = None
    mss: str | None = None
    media: str | None = None
    mediaopt: str | None = None
    # PPP / PPPoE credentials live on a linked ``<ppps>`` entry; we note
    # their presence here with a pointer field so the UI can cross-link.
    blockpriv: bool = False
    blockbogons: bool = False
    # IPv6 prefix-delegation tracking. When ``ipaddrv6 == "track6"``
    # the interface inherits its prefix from the WAN's DHCPv6-PD lease;
    # ``track6_interface`` is the upstream interface key (e.g. ``wan``)
    # and ``track6_prefix_id`` selects which /64 (hex) out of the
    # delegated prefix this interface uses.
    track6_interface: str | None = None
    track6_prefix_id: str | None = None
    # Per-interface DHCPv6 client options (when ``ipaddrv6 == "dhcp6"``).
    dhcp6_ia_pd_len: str | None = None
    dhcp6_prefix_only: bool = False
    adv_dhcp6_prefix_selected_interface: str | None = None


def parse(root: Element) -> list[Interface]:
    el = root.find("interfaces")
    if el is None:
        return []
    out: list[Interface] = []
    # Each direct child is a logical interface. Order is by XML position,
    # which matches pfSense's UI order.
    for child in list(el):
        out.append(
            Interface(
                key=child.tag,
                descr=text(child, "descr"),
                if_=text(child, "if"),
                enabled=bool_flag(child, "enable"),
                ipaddr=text(child, "ipaddr"),
                subnet=text(child, "subnet"),
                gateway=text(child, "gateway"),
                ipaddrv6=text(child, "ipaddrv6"),
                subnetv6=text(child, "subnetv6"),
                gatewayv6=text(child, "gatewayv6"),
                mtu=text(child, "mtu"),
                mss=text(child, "mss"),
                media=text(child, "media"),
                mediaopt=text(child, "mediaopt"),
                blockpriv=bool_flag(child, "blockpriv"),
                blockbogons=bool_flag(child, "blockbogons"),
                track6_interface=text(child, "track6-interface"),
                track6_prefix_id=text(child, "track6-prefix-id"),
                dhcp6_ia_pd_len=text(child, "dhcp6-ia-pd-len"),
                dhcp6_prefix_only=bool_flag(child, "dhcp6prefixonly"),
                adv_dhcp6_prefix_selected_interface=text(
                    child, "adv_dhcp6_prefix_selected_interface"
                ),
            )
        )
    return out
