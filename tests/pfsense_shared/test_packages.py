"""Tests for v0.11.5 package parsers: pfBlockerNG, HAProxy, Suricata, ACME.

Secret-leak checks cover: MaxMind API key (pfBlockerNG), HAProxy
per-server passwords, Snort / Emerging Threats oinkcode (Suricata),
ACME account private keys.
"""

from __future__ import annotations

import textwrap

from pfsense_shared.pfsense_diff import diff_configs
from pfsense_shared.pfsense_parser import parse
from pfsense_shared.pfsense_redact import REDACTED


def _parse(xml: str):
    return parse(textwrap.dedent(xml).strip().encode())


PACKAGES_XML = """
<pfsense>
  <installedpackages>
    <pfblockerng>
      <enable_cb>on</enable_cb>
      <inbound_interface>wan</inbound_interface>
    </pfblockerng>
    <pfblockerngipsettings>
      <enable_cb>on</enable_cb>
      <maxmind_key>LEAKY_MAXMIND_KEY</maxmind_key>
    </pfblockerngipsettings>
    <pfblockerngdnsblsettings>
      <dnsbl>on</dnsbl>
      <dnsbl_mode>unbound_python</dnsbl_mode>
      <dnsbl_port>8053</dnsbl_port>
    </pfblockerngdnsblsettings>
    <pfblockernglistsv4>
      <config>
        <aliasname>BadIPs</aliasname>
        <action>Alias Deny</action>
        <row>
          <state>Enabled</state>
          <url>https://feed.example/badips.txt</url>
          <format>auto</format>
        </row>
      </config>
    </pfblockernglistsv4>
    <ha_backends>
      <item>
        <name>http-fe</name>
        <type>http</type>
        <status>active</status>
        <extaddr>wanip</extaddr>
        <backend_serverpool>web-pool</backend_serverpool>
        <ssloffload>yes</ssloffload>
      </item>
    </ha_backends>
    <ha_pools>
      <item>
        <name>web-pool</name>
        <balance>roundrobin</balance>
        <ha_servers>
          <item>
            <name>w1</name>
            <address>10.0.0.10</address>
            <port>80</port>
            <password>LEAKY_HAPROXY_PASS</password>
          </item>
        </ha_servers>
      </item>
    </ha_pools>
    <suricata>
      <rule>
        <item>
          <uuid>iface-abc</uuid>
          <interface>wan</interface>
          <enable>on</enable>
          <blockoffenders7>on</blockoffenders7>
          <ips_mode>ips_mode_inline</ips_mode>
          <rulesets>emerging-scan.rules||emerging-trojan.rules</rulesets>
        </item>
      </rule>
      <oinkcode>LEAKY_OINKCODE</oinkcode>
    </suricata>
    <acme>
      <enable>on</enable>
      <accountkeys>
        <item>
          <name>prod</name>
          <acmeserver>letsencrypt</acmeserver>
          <email>ops@example</email>
          <accountkey>LEAKY_ACME_KEY_PEM</accountkey>
        </item>
      </accountkeys>
      <certificates>
        <item>
          <name>web.example</name>
          <acmeaccount>prod</acmeaccount>
          <keylength>4096</keylength>
          <a_domainlist>
            <item>
              <name>web.example</name>
              <method>dns_cf</method>
            </item>
          </a_domainlist>
        </item>
      </certificates>
    </acme>
    <unknown_pkg>
      <enable>yes</enable>
      <other>data</other>
    </unknown_pkg>
  </installedpackages>
</pfsense>
"""


def test_pfblockerng_feeds_and_secrets() -> None:
    cfg = _parse(PACKAGES_XML)
    p = cfg.installedpackages
    assert p is not None
    b = p.pfblockerng
    assert b is not None
    assert b.enable_pfblockerng is True
    assert b.ip_enabled is True
    assert b.dnsbl_enabled is True
    assert b.dnsbl_mode == "unbound_python"
    assert b.maxmind_key_configured is True  # never exposes the value
    assert len(b.feeds) == 1
    assert b.feeds[0].url == "https://feed.example/badips.txt"
    assert b.feeds[0].header == "BadIPs"
    # Secret leak check
    assert "LEAKY_MAXMIND_KEY" not in cfg.model_dump_json()


def test_pfblockerng_feed_url_oinkcode_is_scrubbed() -> None:
    """Paid feeds (ET Pro, Snort VRT) embed a subscriber oinkcode directly
    in the feed URL. That credential must not survive into parsed JSON."""
    cfg = _parse(
        """
        <pfsense>
          <installedpackages>
            <pfblockernglistsv4>
              <config>
                <aliasname>ETPro</aliasname>
                <action>Alias Deny</action>
                <row>
                  <state>Enabled</state>
                  <url>https://rules.emergingthreats.net/0123456789abcdef0123456789abcdef01234567/suricata-6.0.0/emerging-all.rules</url>
                  <format>auto</format>
                </row>
              </config>
            </pfblockernglistsv4>
            <pfblockernglistsv6>
              <config>
                <aliasname>SnortVRT</aliasname>
                <action>Alias Deny</action>
                <row>
                  <state>Enabled</state>
                  <url>https://www.snort.org/rules/snortrules-snapshot-2983.tar.gz?oinkcode=deadbeefcafef00ddeadbeefcafef00ddeadbeef</url>
                </row>
              </config>
            </pfblockernglistsv6>
          </installedpackages>
        </pfsense>
        """
    )
    p = cfg.installedpackages
    assert p is not None
    assert p.pfblockerng is not None
    urls = [f.url for f in p.pfblockerng.feeds]
    assert len(urls) == 2
    # Path-segment credential gets a readable placeholder.
    assert "/***oinkcode***/" in (urls[0] or "")
    assert "0123456789abcdef" not in (urls[0] or "")
    # Query-string credential is redacted.
    assert "oinkcode=***redacted***" in (urls[1] or "")
    assert "deadbeefcafef00d" not in (urls[1] or "")
    blob = cfg.model_dump_json()
    assert "0123456789abcdef" not in blob
    assert "deadbeefcafef00d" not in blob


def test_haproxy_frontend_backend_server_password_redacted() -> None:
    cfg = _parse(PACKAGES_XML)
    h = cfg.installedpackages.haproxy  # type: ignore[union-attr]
    assert h is not None
    assert len(h.frontends) == 1
    assert h.frontends[0].name == "http-fe"
    assert h.frontends[0].ssl is True
    assert h.frontends[0].default_backend == "web-pool"
    assert len(h.backends) == 1
    assert h.backends[0].balance == "roundrobin"
    assert len(h.backends[0].servers) == 1
    s = h.backends[0].servers[0]
    assert s.address == "10.0.0.10"
    assert s.port == "80"
    assert s.password == REDACTED
    assert "LEAKY_HAPROXY_PASS" not in cfg.model_dump_json()


def test_suricata_interfaces_and_oinkcode_redacted() -> None:
    cfg = _parse(PACKAGES_XML)
    s = cfg.installedpackages.suricata  # type: ignore[union-attr]
    assert s is not None
    assert s.oinkmaster_configured is True
    assert len(s.interfaces) == 1
    iface = s.interfaces[0]
    assert iface.interface == "wan"
    assert iface.enable is True
    assert iface.blockoffenders7 is True
    assert iface.ips_mode == "ips_mode_inline"
    assert iface.categories == ["emerging-scan.rules", "emerging-trojan.rules"]
    assert "LEAKY_OINKCODE" not in cfg.model_dump_json()


def test_acme_account_keys_and_certs_redacted() -> None:
    cfg = _parse(PACKAGES_XML)
    a = cfg.installedpackages.acme  # type: ignore[union-attr]
    assert a is not None
    assert a.enable is True
    assert len(a.account_keys) == 1
    k = a.account_keys[0]
    assert k.name == "prod"
    assert k.email == "ops@example"
    assert k.accountkey == REDACTED
    assert len(a.certificates) == 1
    c = a.certificates[0]
    assert c.name == "web.example"
    assert c.keylength == "4096"
    assert c.san_list == ["web.example (dns_cf)"]
    assert "LEAKY_ACME_KEY_PEM" not in cfg.model_dump_json()


def test_unknown_packages_surfaced_with_raw_xml() -> None:
    cfg = _parse(PACKAGES_XML)
    ip = cfg.installedpackages
    assert ip is not None
    tags = [u.tag for u in ip.unknown]
    assert tags == ["unknown_pkg"]
    assert ip.unknown[0].entry_count == 2
    assert "<other>data</other>" in ip.unknown[0].xml


def test_diff_detects_added_feed_and_cert() -> None:
    a = _parse(PACKAGES_XML)
    b_xml = PACKAGES_XML.replace(
        "<url>https://feed.example/badips.txt</url>",
        "<url>https://feed.example/badips-v2.txt</url>",
    )
    b = _parse(b_xml)
    d = diff_configs(a, b)
    # Installed-packages diff registers *some* change (feed URL swap).
    assert not d.installedpackages.is_empty


def test_no_installedpackages_returns_none() -> None:
    cfg = _parse("<pfsense></pfsense>")
    assert cfg.installedpackages is None


def test_only_unknown_packages_still_surface() -> None:
    cfg = _parse("""
        <pfsense>
          <installedpackages>
            <weird_pkg><setting>x</setting></weird_pkg>
          </installedpackages>
        </pfsense>
    """)
    ip = cfg.installedpackages
    assert ip is not None
    assert ip.pfblockerng is None
    assert ip.haproxy is None
    assert ip.suricata is None
    assert ip.acme is None
    assert len(ip.unknown) == 1
    assert ip.unknown[0].tag == "weird_pkg"
