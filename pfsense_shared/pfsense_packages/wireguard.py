"""Parses the WireGuard package under ``<installedpackages><wireguard>``.

Modern VPN with two levels of config:

* **Tunnels** (``<tunnels><item>`` — one per ``wg0``, ``wg1``, …) carry
  the interface's listen port + the firewall's own **private key**.
  That private key *identifies* the tunnel endpoint the same way a
  TLS server's private key identifies a web service — leaking it
  lets an attacker impersonate the firewall to any known peer.
  Redacted via ``privatekey`` / ``private_key`` in ``_EXACT``.

* **Peers** (``<peers><item>`` — one per remote endpoint) carry the
  peer's **public key** (not sensitive), an optional
  **preshared-key** (sensitive — AKE pepper shared between the two
  ends), endpoint, and allowed-IPs list. PSK redacts via the
  existing ``presharedkey`` / ``psk`` entries.

The WireGuard package stores peers and tunnels under the same
``<installedpackages><wireguard>`` block; the tunnel ↔ peer linkage
is by the peer's ``<tun>`` field referencing a tunnel name.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact
from pfsense_shared.pfsense_sections._helpers import bool_flag, children, text


class WireGuardTunnel(BaseModel):
    """One WireGuard interface (``wg0``, ``wg1``, …)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    descr: str | None = None
    enabled: bool = False
    listen_port: str | None = None
    mtu: str | None = None
    # Addresses are CIDR-style list in the raw XML; preserved as-is.
    addresses: list[str] = []
    # Comma- or space-separated DNS server list assigned to this
    # tunnel. v0.20.0 — previously silently dropped, but operators
    # using pfSense WireGuard as a client to commercial VPN providers
    # rely on DNS pinning here to avoid leaks.
    dns: str | None = None
    # Firewall's own public key — publishable; peers need it.
    public_key: str | None = None
    # Firewall's own private key — redacted.
    private_key: str | None = None


class WireGuardPeer(BaseModel):
    """One remote peer bound to a tunnel via ``tun``."""

    model_config = ConfigDict(extra="forbid")

    descr: str | None = None
    enabled: bool = False
    # Which tunnel (interface name) this peer is bound to.
    tun: str | None = None
    endpoint: str | None = None
    port: str | None = None
    persistent_keepalive: str | None = None
    allowed_ips: list[str] = []
    public_key: str | None = None  # peer's public key (not secret)
    preshared_key: str | None = None  # redacted


class WireGuardConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tunnels: list[WireGuardTunnel] = []
    peers: list[WireGuardPeer] = []


CONSUMED_TAGS = frozenset({"wireguard"})


def _split_cidr_list(raw: str | None) -> list[str]:
    """WireGuard stores address / allowed-ip lists either comma- or
    space-separated. Normalise to a clean list of non-empty tokens."""
    if not raw:
        return []
    return [tok.strip() for tok in raw.replace(",", " ").split() if tok.strip()]


def _parse_tunnels(wg_el: Element) -> list[WireGuardTunnel]:
    """Walk ``<tunnels><item>`` rows. Older builds stored tunnels
    directly as ``<tunnel>`` children; handle both."""
    container = wg_el.find("tunnels")
    rows: list[Element] = []
    if container is not None:
        rows = children(container, "item")
    if not rows:
        rows = children(wg_el, "tunnel")
    out: list[WireGuardTunnel] = []
    for t in rows:
        name = text(t, "name") or text(t, "tun")
        if not name:
            continue
        # Address list sometimes lives inline (``<address>1.2.3.4/32</address>``)
        # and sometimes as a block with repeated ``<row>`` children that
        # pair ``<address>`` + ``<mask>`` — the pfSense WireGuard package
        # emits the block form on every build since v2.5. Handle both;
        # the block form must join ``address`` + ``mask`` into a CIDR
        # string or the mask silently drops from the rendered list.
        addresses = _split_cidr_list(text(t, "address"))
        addr_block = t.find("addresses")
        if addr_block is not None:
            for row in children(addr_block, "row"):
                addr = text(row, "address")
                mask = text(row, "mask")
                if addr and mask:
                    addresses.append(f"{addr}/{mask}")
                elif addr:
                    addresses.append(addr)
        out.append(
            WireGuardTunnel(
                name=name,
                descr=text(t, "descr") or text(t, "description"),
                enabled=bool_flag(t, "enabled") or bool_flag(t, "enable"),
                listen_port=text(t, "listenport") or text(t, "listen_port"),
                mtu=text(t, "mtu"),
                addresses=addresses,
                dns=text(t, "dns"),
                public_key=text(t, "publickey") or text(t, "public_key"),
                # Redact the private key via the tag name that lives
                # in ``_EXACT``; pass whichever the XML used.
                private_key=redact(
                    "privatekey",
                    text(t, "privatekey") or text(t, "private_key"),
                ),
            )
        )
    return out


def _parse_peers(wg_el: Element) -> list[WireGuardPeer]:
    container = wg_el.find("peers")
    rows: list[Element] = []
    if container is not None:
        rows = children(container, "item")
    if not rows:
        rows = children(wg_el, "peer")
    out: list[WireGuardPeer] = []
    for p in rows:
        # ``allowedips`` can be inline or a ``<row>`` block of
        # ``<address>``/``<mask>`` pairs. Prefer the block when
        # present so masks land on the right token.
        allowed: list[str] = []
        allowed_block = p.find("allowedips")
        if allowed_block is not None:
            for row in children(allowed_block, "row"):
                addr = text(row, "address")
                mask = text(row, "mask")
                if addr and mask:
                    allowed.append(f"{addr}/{mask}")
                elif addr:
                    allowed.append(addr)
            # Fall back to comma-split on the flat form if the block
            # had no children.
            if not allowed:
                allowed = _split_cidr_list(
                    allowed_block.text if allowed_block.text else None
                )
        else:
            allowed = _split_cidr_list(text(p, "allowedips"))
        out.append(
            WireGuardPeer(
                descr=text(p, "descr") or text(p, "description"),
                enabled=bool_flag(p, "enabled") or bool_flag(p, "enable"),
                tun=text(p, "tun"),
                endpoint=text(p, "endpoint"),
                port=text(p, "port"),
                persistent_keepalive=text(p, "persistentkeepalive")
                or text(p, "persistent_keepalive"),
                allowed_ips=allowed,
                public_key=text(p, "publickey") or text(p, "public_key"),
                preshared_key=redact(
                    "presharedkey",
                    text(p, "presharedkey")
                    or text(p, "preshared_key")
                    or text(p, "psk"),
                ),
            )
        )
    return out


def parse(ip: Element) -> WireGuardConfig | None:
    wg = ip.find("wireguard")
    if wg is None:
        return None
    tunnels = _parse_tunnels(wg)
    peers = _parse_peers(wg)
    if not tunnels and not peers:
        # Bare ``<wireguard/>`` with no tunnels or peers — surface an
        # empty config so the operator sees the package is installed.
        return WireGuardConfig()
    return WireGuardConfig(tunnels=tunnels, peers=peers)
