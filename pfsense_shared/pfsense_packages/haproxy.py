"""Parses HAProxy config under ``<installedpackages>``.

HAProxy on pfSense stores config under two sibling tags:
``ha_backends`` (frontends, despite the name pfSense picked) and
``ha_pools`` (backends / server pools). Each carries an ``<item>`` list.

Passwords (auth users for stats/admin, ACL basic-auth entries) run
through the redaction engine via suffix match.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact
from pfsense_shared.pfsense_sections._helpers import bool_flag, children, text


class HaProxyFrontend(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: str | None = None
    type: str | None = None  # http | tcp | ...
    descr: str | None = None
    extaddr: str | None = None
    # Primary listen address(es). pfSense stores many flavours; we
    # flatten to one display string per entry.
    addresses: list[str] = []
    default_backend: str | None = None
    ssl: bool = False
    forwardfor: bool = False


class HaProxyServer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    address: str | None = None
    port: str | None = None
    ssl: bool = False
    status: str | None = None
    weight: str | None = None
    # Per-server auth password — redacted.
    password: str | None = None


class HaProxyBackend(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    descr: str | None = None
    balance: str | None = None
    check_type: str | None = None
    servers: list[HaProxyServer] = []


class HaProxyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enable: bool = False
    advanced: str | None = None
    remotesyslog: str | None = None
    frontends: list[HaProxyFrontend] = []
    backends: list[HaProxyBackend] = []


CONSUMED_TAGS = frozenset(
    {
        "haproxy",
        "ha_backends",
        "ha_pools",
    }
)


def _frontend_addresses(item: Element) -> list[str]:
    """HAProxy frontends store listen addresses under ``<a_extaddr><item>``
    or a flat ``<extaddr>`` field. Normalize to a list of ``host:port``
    strings."""
    out: list[str] = []
    flat = text(item, "extaddr")
    if flat:
        port = text(item, "extaddr_port")
        out.append(f"{flat}:{port}" if port else flat)
    block = item.find("a_extaddr")
    if block is not None:
        for e in children(block, "item"):
            host = text(e, "extaddr") or "?"
            port = text(e, "extaddr_port") or "?"
            out.append(f"{host}:{port}")
    return out


def _server(row: Element) -> HaProxyServer:
    return HaProxyServer(
        name=text(row, "name") or "?",
        address=text(row, "address"),
        port=text(row, "port"),
        ssl=bool_flag(row, "ssl"),
        status=text(row, "status"),
        weight=text(row, "weight"),
        password=redact("password", text(row, "password")),
    )


def parse(ip: Element) -> HaProxyConfig | None:
    """``ip`` is the ``<installedpackages>`` element."""
    root = ip.find("haproxy")
    frontends_el = ip.find("ha_backends")  # naming inversion is pfSense's
    backends_el = ip.find("ha_pools")

    if all(x is None for x in (root, frontends_el, backends_el)):
        return None

    frontends: list[HaProxyFrontend] = []
    if frontends_el is not None:
        for item in children(frontends_el, "item"):
            name = text(item, "name")
            if not name:
                continue
            frontends.append(
                HaProxyFrontend(
                    name=name,
                    status=text(item, "status"),
                    type=text(item, "type"),
                    descr=text(item, "descr"),
                    extaddr=text(item, "extaddr"),
                    addresses=_frontend_addresses(item),
                    default_backend=text(item, "backend_serverpool"),
                    ssl=bool_flag(item, "ssloffload"),
                    forwardfor=bool_flag(item, "forwardfor"),
                )
            )

    backends: list[HaProxyBackend] = []
    if backends_el is not None:
        for item in children(backends_el, "item"):
            name = text(item, "name")
            if not name:
                continue
            servers: list[HaProxyServer] = []
            servers_block = item.find("ha_servers")
            if servers_block is not None:
                for row in children(servers_block, "item"):
                    servers.append(_server(row))
            backends.append(
                HaProxyBackend(
                    name=name,
                    descr=text(item, "descr"),
                    balance=text(item, "balance"),
                    check_type=text(item, "check_type"),
                    servers=servers,
                )
            )

    return HaProxyConfig(
        enable=bool_flag(root, "enable") if root is not None else False,
        advanced=text(root, "advanced") if root is not None else None,
        remotesyslog=text(root, "remotesyslog") if root is not None else None,
        frontends=frontends,
        backends=backends,
    )
