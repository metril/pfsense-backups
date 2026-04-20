"""Parses Telegraf package config under ``<installedpackages>``.

Minimal — pfSense's Telegraf package is a thin wrapper around the
upstream telegraf agent config. We pull out the enable flag, the
output plugin (usually InfluxDB), the target URL, and the token
(redacted).
"""

from __future__ import annotations

import re
from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import REDACTED, redact
from pfsense_shared.pfsense_sections._helpers import bool_flag, text

# Strip embedded basic-auth creds from any URL — both ``user:pass@``
# and the rarer ``user@`` (username-only) forms. InfluxDB v1 accepts
# ``http://user:pass@host:8086/db``, so the output URL can leak both
# the username and password even when they're also stored in their
# own fields. The character class excludes ``:`` so the scheme-port
# suffix (``:8086``) isn't greedily consumed. Replace the credential
# segment with the standard marker so diffs still show "URL changed"
# without leaking the creds.
_URL_BASIC_AUTH_RE: re.Pattern[str] = re.compile(
    r"(://)[^/@\s:]+(?::[^/@\s]*)?@",
)


def _scrub_url(url: str | None) -> str | None:
    if not url:
        return url
    return _URL_BASIC_AUTH_RE.sub(rf"\1{REDACTED}@", url)


class TelegrafConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    interval: str | None = None
    # Output — typically influxdb(v1) or influxdb_v2
    output_plugin: str | None = None
    # URL has any embedded ``user:pass@`` basic-auth segment scrubbed.
    url: str | None = None
    database: str | None = None
    organization: str | None = None
    bucket: str | None = None
    # Redacted — v0.20.0: the username is the operator's metrics-backend
    # identity and is as sensitive as the password it pairs with.
    username: str | None = None
    password: str | None = None
    token: str | None = None


CONSUMED_TAGS = frozenset({"telegraf"})


def parse(ip: Element) -> TelegrafConfig | None:
    el = ip.find("telegraf")
    if el is None:
        return None
    return TelegrafConfig(
        enabled=bool_flag(el, "enable"),
        interval=text(el, "interval"),
        output_plugin=text(el, "output") or text(el, "output_plugin"),
        url=_scrub_url(text(el, "url")),
        database=text(el, "database"),
        organization=text(el, "organization"),
        bucket=text(el, "bucket"),
        username=redact("influxdb_username", text(el, "username")),
        password=redact("password", text(el, "password")),
        token=redact("influxdb_token", text(el, "token") or text(el, "influxdb_token")),
    )
