"""Parses Squid + squidGuard config under ``<installedpackages>``.

Two sibling tags: ``squid`` (proxy cache) and ``squidguard`` (URL
filter). Both carry credentials — proxy auth bind-DN passwords,
LDAP binds, NT admin passwords on some builds. All routed through
the redaction engine.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact
from pfsense_shared.pfsense_sections._helpers import bool_flag, children, text


class SquidConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enable: bool = False
    active_interface: str | None = None
    proxy_port: str | None = None
    transparent_mode: bool = False
    allow_interface: list[str] = []
    # Auth
    auth_method: str | None = None  # "none" | "local" | "ldap" | "radius" | "ntlm"
    auth_realm: str | None = None
    ldap_server: str | None = None
    ldap_binddn: str | None = None
    # Redacted
    ldap_bindpw: str | None = None
    ntlm_domain: str | None = None
    ntlm_admin_username: str | None = None
    ntlm_admin_password: str | None = None


class SquidGuardTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    descr: str | None = None
    domain_list: list[str] = []  # raw lines
    url_list: list[str] = []
    enabled: bool = True


class SquidGuardAcl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    descr: str | None = None
    source: str | None = None
    time_range: str | None = None
    redirect: str | None = None
    enabled: bool = True


class SquidGuardConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    blacklist_enabled: bool = False
    blacklist_url: str | None = None
    strip_path: bool = False
    targets: list[SquidGuardTarget] = []
    acls: list[SquidGuardAcl] = []


class SquidAuthConfig(BaseModel):
    """Auth configuration from ``<squidauth>`` — the "Authentication"
    tab of the Squid package. Separate from ``<squid>``, which carries
    the cache daemon's own LDAP bind credentials for the HTTP proxy.
    This block covers the secondary auth method (LDAP bind or RADIUS
    shared secret used by the per-user auth helper).

    ``ldap_pass`` and ``radius_secret`` are credentials — routed
    through the redaction engine (``ldap_bindpw`` / ``radius_secret``
    tags, both already in ``_EXACT``)."""

    model_config = ConfigDict(extra="forbid")

    auth_method: str | None = None
    ldap_server: str | None = None
    ldap_port: str | None = None
    ldap_binddn: str | None = None
    ldap_pass: str | None = None  # redacted
    ldap_search_base: str | None = None
    ldap_filter: str | None = None
    radius_server: str | None = None
    radius_port: str | None = None
    radius_secret: str | None = None  # redacted
    # NTLM domain-join credentials. Some Squid builds store the
    # Windows machine-account password as ``<nt_pass>`` here — it's
    # distinct from ``<ntlm_admin_password>`` in the main ``<squid>``
    # block. Redacted via the ``nt_pass`` entry in ``_EXACT``.
    nt_user: str | None = None
    nt_pass: str | None = None  # redacted


class SquidBundle(BaseModel):
    """Combined output — Squid + squidGuard sit under ``installedpackages.squid``
    in the ParsedConfig for convenience."""

    model_config = ConfigDict(extra="forbid")

    squid: SquidConfig | None = None
    squidguard: SquidGuardConfig | None = None
    # v0.16.0: sibling sub-package tags. The pfSense Squid package
    # stores cache tuning, remote-ACL, auth, and antivirus settings
    # under their own top-level tags next to ``<squid>``. Presence
    # booleans surface which sub-feature is configured;
    # ``auth`` is structured because it carries credentials that
    # must be routed through the redaction engine (v0.16.1).
    cache_present: bool = False
    remote_present: bool = False
    auth: SquidAuthConfig | None = None
    antivirus_present: bool = False


CONSUMED_TAGS = frozenset(
    {
        "squid",
        "squidguard",
        # v0.16.0 — sibling sub-packages.
        "squidcache",
        "squidremote",
        "squidauth",
        "squidantivirus",
    }
)


def _parse_squid(el: Element | None) -> SquidConfig | None:
    if el is None:
        return None
    allow_raw = text(el, "allow_interface") or ""
    return SquidConfig(
        enable=bool_flag(el, "enable"),
        active_interface=text(el, "active_interface"),
        proxy_port=text(el, "proxy_port"),
        transparent_mode=bool_flag(el, "transparent_proxy"),
        allow_interface=[x.strip() for x in allow_raw.split(",") if x.strip()],
        auth_method=text(el, "auth_method"),
        auth_realm=text(el, "auth_realm"),
        ldap_server=text(el, "ldap_server") or text(el, "auth_server"),
        ldap_binddn=text(el, "ldap_binddn") or text(el, "auth_binddn"),
        ldap_bindpw=redact(
            "ldap_bindpw", text(el, "ldap_bindpw") or text(el, "auth_bindpw")
        ),
        ntlm_domain=text(el, "ntlm_domain"),
        ntlm_admin_username=text(el, "ntlm_admin_username"),
        ntlm_admin_password=redact(
            "ntlm_admin_password", text(el, "ntlm_admin_password")
        ),
    )


def _parse_squidguard(el: Element | None) -> SquidGuardConfig | None:
    if el is None:
        return None
    targets: list[SquidGuardTarget] = []
    targets_block = el.find("destinations")
    if targets_block is None:
        targets_block = el.find("target")
    if targets_block is not None:
        candidates = children(targets_block, "item")
        if not candidates:
            candidates = children(el, "target")
        for t in candidates:
            name = text(t, "name")
            if not name:
                continue
            domains_raw = text(t, "domainlist") or text(t, "domains") or ""
            urls_raw = text(t, "urllist") or text(t, "urls") or ""
            targets.append(
                SquidGuardTarget(
                    name=name,
                    descr=text(t, "descr") or text(t, "description"),
                    domain_list=[
                        s for s in domains_raw.replace(",", " ").split() if s
                    ],
                    url_list=[s for s in urls_raw.replace(",", " ").split() if s],
                    enabled=not bool_flag(t, "disabled"),
                )
            )

    acls: list[SquidGuardAcl] = []
    acls_block = el.find("acls")
    if acls_block is not None:
        acl_candidates = children(acls_block, "item")
        if not acl_candidates:
            acl_candidates = children(el, "acl")
        for a in acl_candidates:
            name = text(a, "name")
            if not name:
                continue
            acls.append(
                SquidGuardAcl(
                    name=name,
                    descr=text(a, "description") or text(a, "descr"),
                    source=text(a, "sources") or text(a, "source"),
                    time_range=text(a, "time"),
                    redirect=text(a, "redirect"),
                    enabled=not bool_flag(a, "disabled"),
                )
            )

    return SquidGuardConfig(
        enabled=bool_flag(el, "enable") or bool_flag(el, "enabled"),
        blacklist_enabled=bool_flag(el, "blacklist"),
        blacklist_url=text(el, "blacklist_url"),
        strip_path=bool_flag(el, "strip_path"),
        targets=targets,
        acls=acls,
    )


def _parse_squidauth(el: Element | None) -> SquidAuthConfig | None:
    """``<squidauth>`` is the Authentication tab's backing store. It
    can carry either inline fields or a single ``<item>`` wrapper
    (package-version dependent). Credentials are always redacted."""
    if el is None:
        return None
    # Unwrap ``<item>`` if present. Using an explicit ``is not None``
    # check — ``find() or el`` would trigger a future-removed truth
    # test on Element, which Python warns about.
    item_el = el.find("item")
    item = item_el if item_el is not None else el
    return SquidAuthConfig(
        auth_method=text(item, "auth_method"),
        ldap_server=text(item, "ldap_server"),
        ldap_port=text(item, "ldap_port"),
        ldap_binddn=text(item, "ldap_user") or text(item, "ldap_binddn"),
        ldap_pass=redact(
            "ldap_bindpw", text(item, "ldap_pass") or text(item, "ldap_bindpw")
        ),
        ldap_search_base=text(item, "ldap_basedomain")
        or text(item, "ldap_search_base"),
        ldap_filter=text(item, "ldap_userattribute")
        or text(item, "ldap_filter"),
        radius_server=text(item, "radius_server"),
        radius_port=text(item, "radius_port"),
        radius_secret=redact("radius_secret", text(item, "radius_secret")),
        nt_user=text(item, "nt_user"),
        nt_pass=redact("nt_pass", text(item, "nt_pass")),
    )


def parse(ip: Element) -> SquidBundle | None:
    sq = _parse_squid(ip.find("squid"))
    sg = _parse_squidguard(ip.find("squidguard"))
    cache = ip.find("squidcache")
    remote = ip.find("squidremote")
    auth = _parse_squidauth(ip.find("squidauth"))
    antivirus = ip.find("squidantivirus")
    if sq is None and sg is None and auth is None and all(
        x is None for x in (cache, remote, antivirus)
    ):
        return None
    return SquidBundle(
        squid=sq,
        squidguard=sg,
        cache_present=cache is not None,
        remote_present=remote is not None,
        auth=auth,
        antivirus_present=antivirus is not None,
    )
