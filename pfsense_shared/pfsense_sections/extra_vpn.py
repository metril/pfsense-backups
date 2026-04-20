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

    # Stable diff key — pfSense assigns a numeric ``pppoeid``.
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


def parse_pppoes(root: Element) -> list[PppoeServerEntry]:
    el = root.find("pppoes")
    if el is None:
        return []
    out: list[PppoeServerEntry] = []
    # pfSense wraps each server in ``<pppoe>``.
    for i, p in enumerate(children(el, "pppoe")):
        pppoeid = text(p, "pppoeid") or str(i)
        users: list[PppoeUser] = []
        for u in children(p, "user"):
            name = text(u, "name")
            if not name:
                continue
            users.append(
                PppoeUser(
                    name=name,
                    ip=text(u, "ip"),
                    password=redact("password", text(u, "password")),
                )
            )
        radius = p.find("radius")
        out.append(
            PppoeServerEntry(
                key=pppoeid,
                mode=text(p, "mode"),
                interface=text(p, "interface"),
                localip=text(p, "localip"),
                remoteip=text(p, "remoteip"),
                descr=text(p, "descr"),
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
