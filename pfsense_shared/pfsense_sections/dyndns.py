"""Parses ``<dyndnses>`` — Dynamic DNS provider entries.

pfSense's Dynamic DNS client supports dozens of providers (Cloudflare,
DuckDNS, Namecheap, DynDNS, GoDaddy, …) all through one schema. Each
``<dyndns>`` child carries provider-specific auth: a username + a
password for classic providers, an API token for modern ones. Both
paths run through the redaction engine (``password`` is an exact match;
token fields route through the ``*_password`` / ``*_secret`` suffix
rules or the explicit ``apikey`` / ``api_key`` entries).
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact

from ._helpers import bool_flag, children, text


class DyndnsEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Stable diff key — provider + host combo. pfSense doesn't assign
    # its own id to dyndns entries.
    key: str
    type: str | None = None  # provider name (cloudflare / duckdns / etc.)
    interface: str | None = None
    host: str | None = None
    domainname: str | None = None
    mx: str | None = None
    descr: str | None = None
    enabled: bool = False
    wildcard: bool = False
    force_update: bool = False
    verboselog: bool = False
    # Auth — redacted. pfSense stores them under <username> (often an
    # API account id) and <password> (the actual secret). Modern
    # providers stash a bearer token in <password> as well; a few
    # builds expose a separate <token> element.
    username: str | None = None
    password: str | None = None
    token: str | None = None


def parse(root: Element) -> list[DyndnsEntry]:
    el = root.find("dyndnses")
    if el is None:
        return []
    out: list[DyndnsEntry] = []
    for d in children(el, "dyndns"):
        provider = text(d, "type")
        host = text(d, "host")
        key = f"{provider or '?'}|{host or text(d, 'domainname') or '?'}"
        out.append(
            DyndnsEntry(
                key=key,
                type=provider,
                interface=text(d, "interface"),
                host=host,
                domainname=text(d, "domainname"),
                mx=text(d, "mx"),
                descr=text(d, "descr"),
                enabled=bool_flag(d, "enable"),
                wildcard=bool_flag(d, "wildcard"),
                force_update=bool_flag(d, "force_update")
                or bool_flag(d, "forceupdate"),
                verboselog=bool_flag(d, "verboselog"),
                # ``username`` is usually a public account id (it
                # renders in the pfSense UI) so it isn't redacted;
                # modern providers store the bearer token under
                # <password>, which is.
                username=text(d, "username"),
                password=redact("password", text(d, "password")),
                # Use a self-documenting redact tag that's in _EXACT
                # (``api_token``) — ``token`` is intentionally not a
                # blanket _EXACT entry since it has benign call sites
                # elsewhere.
                token=redact("api_token", text(d, "token")),
            )
        )
    return out
