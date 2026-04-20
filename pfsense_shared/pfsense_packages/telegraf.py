"""Parses Telegraf package config under ``<installedpackages>``.

Minimal — pfSense's Telegraf package is a thin wrapper around the
upstream telegraf agent config. We pull out the enable flag, the
output plugin (usually InfluxDB), the target URL, and the token
(redacted).
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact
from pfsense_shared.pfsense_sections._helpers import bool_flag, text


class TelegrafConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    interval: str | None = None
    # Output — typically influxdb(v1) or influxdb_v2
    output_plugin: str | None = None
    url: str | None = None
    database: str | None = None
    organization: str | None = None
    bucket: str | None = None
    # Redacted — v1 password or v2 bearer token
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
        url=text(el, "url"),
        database=text(el, "database"),
        organization=text(el, "organization"),
        bucket=text(el, "bucket"),
        username=text(el, "username"),
        password=redact("password", text(el, "password")),
        token=redact("influxdb_token", text(el, "token") or text(el, "influxdb_token")),
    )
