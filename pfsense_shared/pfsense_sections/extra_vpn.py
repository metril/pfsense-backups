"""Parses the two legacy VPN tags that still appear on pfSense ISP /
multi-WAN deployments: ``<l2tp>`` (L2TP server) and ``<pppoes>``
(PPPoE server).

Both carry credentials — per-user passwords and (for L2TP) an
optional RADIUS secret. Every such field routes through the
redaction engine.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact

from ._helpers import bool_flag, children, text


class L2tpUser(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    ip: str | None = None
    password: str | None = None


class L2tpConfig(BaseModel):
    """pfSense's L2TP/IPsec road-warrior server. RADIUS auth + per-user
    passwords are the credential-bearing fields here."""

    model_config = ConfigDict(extra="forbid")

    mode: str | None = None
    interface: str | None = None
    localip: str | None = None
    remoteip: str | None = None
    radius_enabled: bool = False
    radius_server: str | None = None
    radius_secret: str | None = None
    users: list[L2tpUser] = []


def parse_l2tp(root: Element) -> L2tpConfig | None:
    el = root.find("l2tp")
    if el is None:
        return None
    users: list[L2tpUser] = []
    for u in children(el, "user"):
        name = text(u, "name")
        if not name:
            continue
        users.append(
            L2tpUser(
                name=name,
                ip=text(u, "ip"),
                password=redact("password", text(u, "password")),
            )
        )
    radius = el.find("radius")
    return L2tpConfig(
        mode=text(el, "mode"),
        interface=text(el, "interface"),
        localip=text(el, "localip"),
        remoteip=text(el, "remoteip"),
        radius_enabled=bool_flag(radius, "enable") if radius is not None else False,
        radius_server=text(radius, "server") if radius is not None else None,
        radius_secret=redact(
            "radius_secret",
            text(radius, "secret") if radius is not None else None,
        ),
        users=users,
    )


class PppoeUser(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    ip: str | None = None
    password: str | None = None


class PppoeServerEntry(BaseModel):
    """A single PPPoE server instance. pfSense supports multiple, each
    listening on its own WAN interface."""

    model_config = ConfigDict(extra="forbid")

    # Stable diff key — pfSense assigns a numeric ``pppoeid``. When
    # missing we prefer the interface + descr combo over a loop index
    # so diff key identity doesn't depend on XML child order.
    key: str
    mode: str | None = None
    interface: str | None = None
    localip: str | None = None
    remoteip: str | None = None
    descr: str | None = None
    radius_enabled: bool = False
    radius_server: str | None = None
    radius_secret: str | None = None
    users: list[PppoeUser] = []


def _parse_pppoe_users(raw: str | None) -> list[PppoeUser]:
    """pfSense encodes PPPoE-server users as a single ``<username>``
    element whose text is a space-separated list of
    ``name:base64password:ip`` tuples. The IP half is optional.
    We surface each user as a structured entry with the password
    redacted — the raw base64 value would reconstruct the plaintext
    once decoded, so redacting is mandatory.
    """
    if not raw:
        return []
    out: list[PppoeUser] = []
    for tok in raw.strip().split():
        parts = tok.split(":")
        if not parts or not parts[0]:
            continue
        name = parts[0]
        pw = parts[1] if len(parts) > 1 else None
        ip = parts[2] if len(parts) > 2 else None
        out.append(
            PppoeUser(
                name=name,
                ip=ip or None,
                password=redact("password", pw),
            )
        )
    return out


def parse_pppoes(root: Element) -> list[PppoeServerEntry]:
    el = root.find("pppoes")
    if el is None:
        return []
    out: list[PppoeServerEntry] = []
    # pfSense wraps each server in ``<pppoe>``. Each has a flat
    # ``<username>`` field (colon-encoded users) rather than nested
    # ``<user>`` children.
    for p in children(el, "pppoe"):
        iface = text(p, "interface")
        descr = text(p, "descr")
        pppoeid = text(p, "pppoeid")
        # Stable diff key: prefer the numeric pppoeid; fall back to a
        # content-derived composite that's stable across re-orderings.
        key = pppoeid or f"{iface or '?'}|{descr or '?'}"
        users = _parse_pppoe_users(text(p, "username"))
        radius = p.find("radius")
        out.append(
            PppoeServerEntry(
                key=key,
                mode=text(p, "mode"),
                interface=iface,
                localip=text(p, "localip"),
                remoteip=text(p, "remoteip"),
                descr=descr,
                radius_enabled=bool_flag(radius, "enable") if radius is not None else False,
                radius_server=text(radius, "server") if radius is not None else None,
                radius_secret=redact(
                    "radius_secret",
                    text(radius, "secret") if radius is not None else None,
                ),
                users=users,
            )
        )
    return out
