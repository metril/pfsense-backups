"""Tests for v0.12.0 package parsers: squid / squidGuard, FreeRADIUS,
Telegraf, FRR (BGP + OSPF), and Zabbix agent/proxy.

Redaction coverage is the load-bearing assertion — each package gets
at least one known-secret field whose value must not appear anywhere
in ``ParsedConfig.model_dump_json()``.
"""

from __future__ import annotations

import textwrap

from pfsense_shared.pfsense_parser import parse
from pfsense_shared.pfsense_redact import REDACTED


def _parse(xml: str):
    return parse(textwrap.dedent(xml).strip().encode())


PACKAGES_XML = """
<pfsense>
  <installedpackages>
    <squid>
      <enable/>
      <active_interface>lan</active_interface>
      <proxy_port>3128</proxy_port>
      <transparent_proxy/>
      <allow_interface>lan,opt1</allow_interface>
      <auth_method>ldap</auth_method>
      <auth_realm>Corp</auth_realm>
      <ldap_server>ldap.corp.example</ldap_server>
      <ldap_binddn>cn=bind,dc=corp,dc=example</ldap_binddn>
      <ldap_bindpw>LEAKY_SQUID_LDAP_BINDPW</ldap_bindpw>
      <ntlm_domain>CORP</ntlm_domain>
      <ntlm_admin_username>svc-squid</ntlm_admin_username>
      <ntlm_admin_password>LEAKY_SQUID_NTLM_PW</ntlm_admin_password>
    </squid>
    <squidguard>
      <enable>on</enable>
      <blacklist>on</blacklist>
      <blacklist_url>https://example.com/bl.tar.gz</blacklist_url>
    </squidguard>
    <freeradiussettings>
      <varsettingsenable>on</varsettingsenable>
    </freeradiussettings>
    <freeradius>
      <config>
        <varsection>client</varsection>
        <varclientname>sw1</varclientname>
        <varclientip>10.0.0.2</varclientip>
        <varclientsharedsecret>LEAKY_RADIUS_NAS_SECRET</varclientsharedsecret>
        <varclientnastype>cisco</varclientnastype>
      </config>
      <config>
        <varsection>user</varsection>
        <varusersname>alice</varusersname>
        <varuserspassword>LEAKY_RADIUS_USER_PW</varuserspassword>
        <varusersauthtype>Clear-Text-Password</varusersauthtype>
      </config>
      <config>
        <varsection>interface</varsection>
        <varinterfaceipaddress>*</varinterfaceipaddress>
        <varinterfaceport>1812</varinterfaceport>
        <varinterfaceiptype>auth</varinterfaceiptype>
      </config>
    </freeradius>
    <telegraf>
      <enable/>
      <output>influxdb_v2</output>
      <url>https://influx.example:8086</url>
      <organization>ops</organization>
      <bucket>metrics</bucket>
      <token>LEAKY_INFLUX_V2_TOKEN</token>
    </telegraf>
    <frrglobal>
      <enable/>
      <routerid>10.0.0.1</routerid>
    </frrglobal>
    <frrbgp>
      <enablebgp/>
      <asnum>65001</asnum>
    </frrbgp>
    <frrbgpneighbors>
      <item>
        <name>peer-vendor</name>
        <peer_address>10.0.0.2</peer_address>
        <remote_as>65002</remote_as>
        <password>LEAKY_BGP_MD5_PW</password>
      </item>
    </frrbgpneighbors>
    <frrospf>
      <enableospf/>
      <routerid>10.0.0.1</routerid>
    </frrospf>
    <frrospfinterfaces>
      <item>
        <interface>wan</interface>
        <area>0.0.0.0</area>
        <hello_interval>10</hello_interval>
        <md5password>LEAKY_OSPF_MD5_PW</md5password>
      </item>
    </frrospfinterfaces>
    <zabbixagentlts>
      <agentenabled/>
      <server>zabbix.corp.example</server>
      <hostname>gw-edge</hostname>
      <listenport>10050</listenport>
      <tlspskidentity>gw-edge</tlspskidentity>
      <tlspsk>LEAKY_ZABBIX_TLS_PSK</tlspsk>
    </zabbixagentlts>
    <zabbixproxylts>
      <proxyenabled/>
      <server>zabbix.corp.example</server>
      <hostname>gw-proxy</hostname>
      <tlspskidentity>gw-proxy</tlspskidentity>
      <tlspsk>LEAKY_ZABBIX_PROXY_PSK</tlspsk>
    </zabbixproxylts>
  </installedpackages>
</pfsense>
"""


def test_squid_and_squidguard_parse_with_redaction() -> None:
    cfg = _parse(PACKAGES_XML)
    sq = cfg.installedpackages.squid  # type: ignore[union-attr]
    assert sq is not None
    assert sq.squid is not None
    s = sq.squid
    assert s.enable is True
    assert s.auth_method == "ldap"
    assert s.ldap_server == "ldap.corp.example"
    assert s.ldap_bindpw == REDACTED
    assert s.ntlm_admin_password == REDACTED
    assert s.allow_interface == ["lan", "opt1"]
    assert sq.squidguard is not None
    assert sq.squidguard.enabled is True
    assert sq.squidguard.blacklist_url == "https://example.com/bl.tar.gz"


def test_freeradius_clients_users_interfaces() -> None:
    cfg = _parse(PACKAGES_XML)
    fr = cfg.installedpackages.freeradius  # type: ignore[union-attr]
    assert fr is not None
    assert fr.enabled is True
    assert len(fr.clients) == 1
    assert fr.clients[0].name == "sw1"
    assert fr.clients[0].shared_secret == REDACTED
    assert fr.clients[0].nas_type == "cisco"
    assert len(fr.users) == 1
    assert fr.users[0].name == "alice"
    assert fr.users[0].password == REDACTED
    assert len(fr.interfaces) == 1
    assert fr.interfaces[0].port == "1812"


def test_telegraf_config_redacts_token() -> None:
    cfg = _parse(PACKAGES_XML)
    t = cfg.installedpackages.telegraf  # type: ignore[union-attr]
    assert t is not None
    assert t.enabled is True
    assert t.url == "https://influx.example:8086"
    assert t.bucket == "metrics"
    assert t.organization == "ops"
    assert t.token == REDACTED


def test_frr_bgp_and_ospf_auth_redacted() -> None:
    cfg = _parse(PACKAGES_XML)
    frr = cfg.installedpackages.frr  # type: ignore[union-attr]
    assert frr is not None
    assert frr.bgp is not None
    assert frr.bgp.enabled is True
    assert frr.bgp.local_as == "65001"
    assert len(frr.bgp.neighbors) == 1
    n = frr.bgp.neighbors[0]
    assert n.remote_as == "65002"
    assert n.password == REDACTED
    assert frr.ospf is not None
    assert frr.ospf.enabled is True
    assert len(frr.ospf.interfaces) == 1
    i = frr.ospf.interfaces[0]
    assert i.interface == "wan"
    assert i.area == "0.0.0.0"
    assert i.md5_password == REDACTED


def test_zabbix_agent_and_proxy_psk_redacted() -> None:
    cfg = _parse(PACKAGES_XML)
    zb = cfg.installedpackages.zabbix  # type: ignore[union-attr]
    assert zb is not None
    assert zb.agent is not None
    assert zb.agent.server == "zabbix.corp.example"
    assert zb.agent.hostname == "gw-edge"
    assert zb.agent.tls_psk == REDACTED
    assert zb.proxy is not None
    assert zb.proxy.hostname == "gw-proxy"
    assert zb.proxy.tls_psk == REDACTED


def test_no_package_secrets_anywhere_in_parsed_output() -> None:
    cfg = _parse(PACKAGES_XML)
    blob = cfg.model_dump_json()
    for leak in (
        "LEAKY_SQUID_LDAP_BINDPW",
        "LEAKY_SQUID_NTLM_PW",
        "LEAKY_RADIUS_NAS_SECRET",
        "LEAKY_RADIUS_USER_PW",
        "LEAKY_INFLUX_V2_TOKEN",
        "LEAKY_BGP_MD5_PW",
        "LEAKY_OSPF_MD5_PW",
        "LEAKY_ZABBIX_TLS_PSK",
        "LEAKY_ZABBIX_PROXY_PSK",
    ):
        assert leak not in blob, f"{leak!r} leaked into parsed output"


def test_unknown_packages_dispatcher_still_surfaces_them() -> None:
    """Regression — adding 5 new known packages shouldn't hide unknowns."""
    cfg = _parse("""
        <pfsense>
          <installedpackages>
            <brand_new_thing><enable/></brand_new_thing>
            <squid><enable/></squid>
          </installedpackages>
        </pfsense>
    """)
    assert cfg.installedpackages is not None
    assert [u.tag for u in cfg.installedpackages.unknown] == ["brand_new_thing"]
    # squid still recognized
    assert cfg.installedpackages.squid is not None
