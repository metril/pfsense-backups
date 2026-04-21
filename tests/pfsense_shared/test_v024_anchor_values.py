"""Tests for pfsense_shared.pfsense_anchor_values — the helper that
powers the v0.24.0 anchor-history (per-field blame) endpoint.

Focus: every anchor-id namespace the frontend emits resolves to a
useful value, and missing anchors surface as ``None`` rather than
raising. Sample XML kept small — these tests exist to catch a drift
between the resolver's scope table and the frontend's ``itemId`` /
``fieldId`` helpers.
"""

from __future__ import annotations

import textwrap

from pfsense_shared.pfsense_anchor_values import resolve_anchor_value
from pfsense_shared.pfsense_parser import parse


def _cfg(xml: str):
    return parse(textwrap.dedent(xml).strip().encode())


SAMPLE_XML = """
<pfsense>
  <system>
    <hostname>gw01</hostname>
    <domain>example.com</domain>
    <enablesshd>on</enablesshd>
    <user>
      <name>admin</name>
      <descr>Admin User</descr>
    </user>
    <group>
      <name>admins</name>
    </group>
    <authserver>
      <name>ldap-corp</name>
      <type>ldap</type>
    </authserver>
  </system>
  <filter>
    <rule>
      <tracker>1706288423</tracker>
      <type>pass</type>
      <interface>lan</interface>
      <descr>allow lan</descr>
    </rule>
  </filter>
  <nat>
    <rule>
      <tracker>2200</tracker>
      <interface>wan</interface>
      <target>10.0.0.5</target>
    </rule>
  </nat>
  <aliases>
    <alias>
      <name>RFC1918</name>
      <address>10.0.0.0/8 172.16.0.0/12 192.168.0.0/16</address>
    </alias>
  </aliases>
  <interfaces>
    <lan><if>em1</if><descr>LAN</descr></lan>
  </interfaces>
  <vlans>
    <vlan><vlanif>em0.100</vlanif><tag>100</tag></vlan>
  </vlans>
  <gateways>
    <gateway_item><name>WAN_DHCP</name></gateway_item>
    <gateway_group><name>FAILOVER</name></gateway_group>
  </gateways>
  <schedules>
    <schedule><name>Weekends</name></schedule>
  </schedules>
  <ca><refid>ca_abc</refid></ca>
  <cert><refid>cert_abc</refid></cert>
  <crl><refid>crl_abc</refid></crl>
  <openvpn>
    <openvpn-server><vpnid>1</vpnid></openvpn-server>
    <openvpn-client><vpnid>2</vpnid></openvpn-client>
  </openvpn>
  <ipsec>
    <phase1><ikeid>5</ikeid></phase1>
  </ipsec>
  <load_balancer>
    <lbpool><name>web-pool</name></lbpool>
  </load_balancer>
</pfsense>
"""


def test_field_anchors_resolve_to_scalars():
    cfg = _cfg(SAMPLE_XML)
    assert resolve_anchor_value(cfg, "field-system-hostname") == "gw01"
    assert resolve_anchor_value(cfg, "field-system-domain") == "example.com"
    # Booleans render as ``yes``/``no`` for compact blame display.
    assert resolve_anchor_value(cfg, "field-system-enablesshd") == "yes"


def test_row_anchors_resolve_to_dicts():
    import re

    cfg = _cfg(SAMPLE_XML)
    # Firewall + NAT rules are keyed by the parser's synthesized
    # ``r.key`` — ``tracker:1706288423`` for the test rule,
    # ``hash:…`` for the NAT. Compute from the parsed row so the
    # test doesn't hard-code the sanitised form.
    rule_row = cfg.firewall_rules[0]
    safe_rule_key = re.sub(r"[^A-Za-z0-9_-]", "_", rule_row.key)
    rule = resolve_anchor_value(cfg, f"xref-rule-{safe_rule_key}")
    assert isinstance(rule, dict)
    assert rule["type"] == "pass"
    assert rule["descr"] == "allow lan"

    nat_row = cfg.nat_rules[0]
    safe_nat_key = re.sub(r"[^A-Za-z0-9_-]", "_", nat_row.key)
    nat = resolve_anchor_value(cfg, f"xref-nat-{safe_nat_key}")
    assert isinstance(nat, dict)
    assert nat["target"] == "10.0.0.5"

    alias = resolve_anchor_value(cfg, "xref-alias-RFC1918")
    assert isinstance(alias, dict)
    assert alias["name"] == "RFC1918"


def test_every_row_scope_resolves():
    """One assertion per row scope so drift between the resolver's
    ``_ROW_SCOPES`` table and the frontend's ``itemId`` /
    ``rowAnchorId`` helpers is caught at test time."""
    cfg = _cfg(SAMPLE_XML)
    pairs = [
        ("xref-interface-lan", "if_", "em1"),
        ("xref-vlan-em0.100", "tag", "100"),
        ("xref-gateway-WAN_DHCP", "name", "WAN_DHCP"),
        ("xref-gateway_group-FAILOVER", "name", "FAILOVER"),
        ("xref-schedule-Weekends", "name", "Weekends"),
        ("xref-ca-ca_abc", "refid", "ca_abc"),
        ("xref-cert-cert_abc", "refid", "cert_abc"),
        ("xref-crl-crl_abc", "refid", "crl_abc"),
        ("xref-authserver-ldap-corp", "name", "ldap-corp"),
        ("xref-openvpn_server-1", "vpnid", "1"),
        ("xref-openvpn_client-2", "vpnid", "2"),
        ("xref-ipsec_phase1-5", "ikeid", "5"),
        ("xref-lb_pool-web-pool", "name", "web-pool"),
        ("xref-user-admin", "name", "admin"),
        ("xref-group-admins", "name", "admins"),
    ]
    for anchor, expected_key, expected_value in pairs:
        got = resolve_anchor_value(cfg, anchor)
        assert isinstance(got, dict), f"{anchor} should resolve"
        assert got.get(expected_key) == expected_value, (
            f"{anchor}: {expected_key}={got.get(expected_key)!r} wanted {expected_value!r}"
        )


def test_missing_anchor_returns_none():
    """Rows that don't exist in this backup (deleted later, created
    earlier, etc.) resolve to None so the blame drawer can label
    them as absent rather than raising."""
    cfg = _cfg(SAMPLE_XML)
    assert resolve_anchor_value(cfg, "xref-rule-tracker_9999999") is None
    assert resolve_anchor_value(cfg, "xref-alias-does-not-exist") is None
    assert resolve_anchor_value(cfg, "field-system-doesnotexist") is None


def test_every_singleton_section_resolves():
    """``_SINGLETON_PATH`` must cover every non-row section the
    frontend might emit a ``field-*`` or ``section-*`` anchor for.
    Package singletons use dotted descent into
    ``installedpackages``; this test exercises the descent."""
    xml = """
    <pfsense>
      <theme>Dark</theme>
      <diag>
        <shownoaliases>on</shownoaliases>
      </diag>
      <installedpackages>
        <avahi>
          <enable>on</enable>
        </avahi>
        <miniupnpd>
          <enable_upnp>on</enable_upnp>
        </miniupnpd>
        <telegraf>
          <url>http://host:8086</url>
        </telegraf>
      </installedpackages>
    </pfsense>
    """
    cfg = _cfg(xml)
    # ThemePreference stores the theme name under ``name``.
    assert resolve_anchor_value(cfg, "field-theme-name") == "Dark"
    assert resolve_anchor_value(cfg, "field-diag-shownoaliases") == "yes"
    assert resolve_anchor_value(cfg, "field-avahi-enable") == "yes"
    assert resolve_anchor_value(cfg, "field-miniupnpd-enable_upnp") == "yes"
    assert resolve_anchor_value(cfg, "field-telegraf-url") == "http://host:8086"


def test_interface_group_anchor_resolves():
    """``interface_group`` is a full ``RefKind`` on the frontend but
    was missing from ``_ROW_SCOPES`` in v0.22.0–v0.24.0. Resolver must
    find the group by ``ifname`` so the blame drawer can show it."""
    xml = """
    <pfsense>
      <ifgroups>
        <ifgroupentry>
          <ifname>VPN</ifname>
          <members>wan lan</members>
          <descr>VPN peers</descr>
        </ifgroupentry>
      </ifgroups>
    </pfsense>
    """
    cfg = _cfg(xml)
    got = resolve_anchor_value(cfg, "xref-interface_group-VPN")
    assert isinstance(got, dict)
    assert got["ifname"] == "VPN"


def test_sanitised_key_matching():
    """Trackers with non-ident chars (``:`` / ``.`` / ``|``) get
    sanitised to ``_`` in the frontend anchor id. The resolver
    sanitises candidate row keys (``tracker:fw:rule.42``) the same
    way when matching so the two sides agree."""
    xml = """
    <pfsense>
      <filter>
        <rule>
          <tracker>fw:rule.42</tracker>
          <type>pass</type>
        </rule>
      </filter>
    </pfsense>
    """
    cfg = _cfg(xml)
    # Parser produces ``r.key = "tracker:fw:rule.42"``; frontend
    # sanitises that to ``tracker_fw_rule_42``. Backend must match.
    assert resolve_anchor_value(cfg, "xref-rule-tracker_fw_rule_42") is not None


def test_malformed_anchor_returns_none():
    cfg = _cfg(SAMPLE_XML)
    assert resolve_anchor_value(cfg, "not-a-real-anchor") is None
    assert resolve_anchor_value(cfg, "xref-") is None
    assert resolve_anchor_value(cfg, "") is None
