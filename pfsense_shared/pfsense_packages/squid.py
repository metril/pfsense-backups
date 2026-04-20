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


class SquidBundle(BaseModel):
    """Combined output — Squid + squidGuard sit under ``installedpackages.squid``
    in the ParsedConfig for convenience."""

    model_config = ConfigDict(extra="forbid")

    squid: SquidConfig | None = None
    squidguard: SquidGuardConfig | None = None


CONSUMED_TAGS = frozenset({"squid", "squidguard"})


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


def parse(ip: Element) -> SquidBundle | None:
    sq = _parse_squid(ip.find("squid"))
    sg = _parse_squidguard(ip.find("squidguard"))
    if sq is None and sg is None:
        return None
    return SquidBundle(squid=sq, squidguard=sg)
