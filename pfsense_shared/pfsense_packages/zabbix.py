"""Parses Zabbix agent / proxy package config under ``<installedpackages>``.

The pfSense Zabbix packages come in agent and proxy flavours; each
stores the Zabbix server URL, optional encryption PSK (redacted), and
hostname metadata. We parse both if present.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact
from pfsense_shared.pfsense_sections._helpers import bool_flag, text


class ZabbixAgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    server: str | None = None
    serveractive: str | None = None
    hostname: str | None = None
    listenport: str | None = None
    # TLS PSK identity + PSK are both sensitive; redact the PSK bytes.
    tls_psk_identity: str | None = None
    tls_psk: str | None = None


class ZabbixProxyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    server: str | None = None
    hostname: str | None = None
    listenport: str | None = None
    tls_psk_identity: str | None = None
    tls_psk: str | None = None


class ZabbixBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: ZabbixAgentConfig | None = None
    proxy: ZabbixProxyConfig | None = None


CONSUMED_TAGS = frozenset(
    {"zabbixagentlts", "zabbixproxylts", "zabbixagent", "zabbixproxy"}
)


def _parse_agent(el: Element | None) -> ZabbixAgentConfig | None:
    if el is None:
        return None
    return ZabbixAgentConfig(
        enabled=bool_flag(el, "agentenabled") or bool_flag(el, "enable"),
        server=text(el, "server"),
        serveractive=text(el, "serveractive"),
        hostname=text(el, "hostname"),
        listenport=text(el, "listenport"),
        tls_psk_identity=text(el, "tlspskidentity"),
        tls_psk=redact("tlspsk", text(el, "tlspsk") or text(el, "tls_psk")),
    )


def _parse_proxy(el: Element | None) -> ZabbixProxyConfig | None:
    if el is None:
        return None
    return ZabbixProxyConfig(
        enabled=bool_flag(el, "proxyenabled") or bool_flag(el, "enable"),
        server=text(el, "server"),
        hostname=text(el, "hostname"),
        listenport=text(el, "listenport"),
        tls_psk_identity=text(el, "tlspskidentity"),
        tls_psk=redact("tlspsk", text(el, "tlspsk") or text(el, "tls_psk")),
    )


def parse(ip: Element) -> ZabbixBundle | None:
    agent_el = ip.find("zabbixagentlts")
    if agent_el is None:
        agent_el = ip.find("zabbixagent")
    proxy_el = ip.find("zabbixproxylts")
    if proxy_el is None:
        proxy_el = ip.find("zabbixproxy")
    agent = _parse_agent(agent_el)
    proxy = _parse_proxy(proxy_el)
    if agent is None and proxy is None:
        return None
    return ZabbixBundle(agent=agent, proxy=proxy)
