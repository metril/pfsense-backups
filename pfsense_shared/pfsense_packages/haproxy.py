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


class HaProxyAcl(BaseModel):
    """One ACL row on a frontend — these drive ``use_backend`` and
    ``http-request`` decisions. Previously dropped entirely; without
    them an operator can't read a frontend's routing logic."""

    model_config = ConfigDict(extra="forbid")

    name: str
    expression: str | None = None
    value: str | None = None
    casesensitive: bool = False
    inverse: bool = False


class HaProxyAction(BaseModel):
    """One action row on a frontend (``a_actionitems``) — pairs an
    action verb (``use_backend``, ``http-request set-header``, …) with
    an ACL condition."""

    model_config = ConfigDict(extra="forbid")

    action: str | None = None
    acl: str | None = None
    # ``parameters`` is a free-form value (header name+value, backend
    # ref, redirect URL, …). Surfaced verbatim.
    parameters: str | None = None


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
    # v0.43.0 — SSL / TLS frontend tuning. Each entry references one
    # of the pfSense cert refids. These fields drive what the
    # frontend accepts: which certs, which ciphers/protocols, whether
    # client-cert auth is required.
    ssloffloadcert: str | None = None
    dcertadv: str | None = None  # default cert "advanced" flag
    clientcert_ca: str | None = None  # CA ref for mTLS validation
    clientcert_crl: str | None = None  # CRL ref for mTLS revocation
    sslclientcert_required: bool = False
    sslciphers: str | None = None
    sslprotocols: str | None = None
    advanced: str | None = None  # raw "advanced" textarea
    # ACLs + actions drive routing decisions and request rewriting.
    acls: list[HaProxyAcl] = []
    actions: list[HaProxyAction] = []


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
    # v0.43.0 — server tuning. ``maxconn`` caps concurrent backend
    # connections; ``sslservercertverify`` toggles upstream cert
    # verification; ``advanced`` carries raw extra options.
    maxconn: str | None = None
    sslservercertverify: bool = False
    advanced: str | None = None


class HaProxyBackend(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    descr: str | None = None
    balance: str | None = None
    check_type: str | None = None
    servers: list[HaProxyServer] = []
    # v0.43.0 — timeouts + retries + health-check + cookie persistence.
    # All of these are operationally critical when debugging "why is
    # this backend marked down" or "why does the session pin to
    # server X" questions.
    connection_timeout: str | None = None
    server_timeout: str | None = None
    retries: str | None = None
    httpcheck_method: str | None = None  # GET | HEAD | POST | OPTIONS
    monitor_uri: str | None = None
    monitor_httpversion: str | None = None
    check_interval: str | None = None
    persist_cookie_enabled: bool = False
    persist_cookie_name: str | None = None
    persist_cookie_mode: str | None = None  # insert | rewrite | prefix
    advanced: str | None = None  # raw "advanced" textarea


class HaProxyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enable: bool = False
    advanced: str | None = None
    remotesyslog: str | None = None
    frontends: list[HaProxyFrontend] = []
    backends: list[HaProxyBackend] = []
    # v0.43.0 — global stanza fields. ``maxconn`` is the box-wide
    # concurrent connection cap; ``nbthread`` sets thread count;
    # ``ssldefaultdhparam`` defines the DH parameter size; the
    # logging fields control which facility/level/format HAProxy
    # writes to.
    maxconn: str | None = None
    nbthread: str | None = None
    nbproc: str | None = None
    hard_stop_after: str | None = None
    ssldefaultdhparam: str | None = None
    log_facility: str | None = None
    log_level: str | None = None
    log_send_hostname: str | None = None
    # Local stats listener (the in-pfSense HAProxy stats page).
    localstats_port: str | None = None
    localstats_refresh: str | None = None
    localstats_sticktable_views: bool = False
    # Carp / fault-tolerance hooks — non-secret, but useful when
    # debugging an HA pair.
    carpdev: str | None = None
    enable_iface: str | None = None


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
        maxconn=text(row, "maxconn"),
        sslservercertverify=bool_flag(row, "sslservercertverify"),
        advanced=text(row, "advanced"),
    )


def _acls(item: Element) -> list[HaProxyAcl]:
    """``<ha_acls>`` carries one ``<item>`` per ACL row."""
    block = item.find("ha_acls")
    if block is None:
        return []
    out: list[HaProxyAcl] = []
    for row in children(block, "item"):
        name = text(row, "name")
        if not name:
            continue
        out.append(
            HaProxyAcl(
                name=name,
                expression=text(row, "expression"),
                value=text(row, "value"),
                casesensitive=bool_flag(row, "casesensitive"),
                inverse=bool_flag(row, "inverse"),
            )
        )
    return out


def _actions(item: Element) -> list[HaProxyAction]:
    """``<a_actionitems>`` rows pair an action verb with an ACL ref."""
    block = item.find("a_actionitems")
    if block is None:
        return []
    out: list[HaProxyAction] = []
    for row in children(block, "item"):
        # Some package versions store the verb under <action>, others
        # use the more specific <use_backendrule>, <http-response>,
        # etc. ``action`` is the canonical column in the UI — fall
        # back to scanning for any populated verb-like child if it's
        # missing.
        verb = text(row, "action")
        if not verb:
            for cand in (
                "use_backendrule",
                "http-request",
                "http-response",
                "tcp-request",
                "tcp-response",
            ):
                v = text(row, cand)
                if v:
                    verb = cand
                    break
        params = text(row, "parameters") or text(row, "value")
        out.append(
            HaProxyAction(
                action=verb,
                acl=text(row, "acl"),
                parameters=params,
            )
        )
    return out


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
                    ssloffloadcert=text(item, "ssloffloadcert"),
                    dcertadv=text(item, "dcertadv"),
                    clientcert_ca=text(item, "clientcert_ca"),
                    clientcert_crl=text(item, "clientcert_crl"),
                    sslclientcert_required=bool_flag(item, "ssloffloadclientcert"),
                    sslciphers=text(item, "ssl_ciphers")
                    or text(item, "sslciphers"),
                    sslprotocols=text(item, "ssl_protocols")
                    or text(item, "sslprotocols"),
                    advanced=text(item, "advanced"),
                    acls=_acls(item),
                    actions=_actions(item),
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
                    connection_timeout=text(item, "connection_timeout"),
                    server_timeout=text(item, "server_timeout"),
                    retries=text(item, "retries"),
                    httpcheck_method=text(item, "httpcheck_method"),
                    monitor_uri=text(item, "monitor_uri"),
                    monitor_httpversion=text(item, "monitor_httpversion"),
                    check_interval=text(item, "check_frequency")
                    or text(item, "check_interval"),
                    persist_cookie_enabled=bool_flag(item, "persist_cookie_enabled"),
                    persist_cookie_name=text(item, "persist_cookie_name"),
                    persist_cookie_mode=text(item, "persist_cookie_mode"),
                    advanced=text(item, "advanced"),
                )
            )

    return HaProxyConfig(
        enable=bool_flag(root, "enable") if root is not None else False,
        advanced=text(root, "advanced") if root is not None else None,
        remotesyslog=text(root, "remotesyslog") if root is not None else None,
        frontends=frontends,
        backends=backends,
        maxconn=text(root, "maxconn") if root is not None else None,
        nbthread=text(root, "nbthread") if root is not None else None,
        nbproc=text(root, "nbproc") if root is not None else None,
        hard_stop_after=text(root, "hard_stop_after") if root is not None else None,
        ssldefaultdhparam=text(root, "ssldefaultdhparam")
        if root is not None
        else None,
        log_facility=text(root, "log-facility") if root is not None else None,
        log_level=text(root, "log-level") if root is not None else None,
        log_send_hostname=text(root, "log-send-hostname")
        if root is not None
        else None,
        localstats_port=text(root, "localstats_port") if root is not None else None,
        localstats_refresh=text(root, "localstats_refresh")
        if root is not None
        else None,
        localstats_sticktable_views=bool_flag(root, "localstats_sticktable_views")
        if root is not None
        else False,
        carpdev=text(root, "carpdev") if root is not None else None,
        enable_iface=text(root, "enable_iface") if root is not None else None,
    )
