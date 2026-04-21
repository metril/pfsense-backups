"""Tests for pfsense_shared.pfsense_positions — the anchorId → source-
line map that drives v0.22.0's Structured ↔ Raw XML tab-switch sync.

Focus: the keys emitted MUST match what the viewer renders. If these
drift apart, the tab switch silently misses — the backend has the
data but the frontend doesn't find it. Every row type in the
frontend's xref/row anchor conventions gets at least one positive
assertion.
"""

from __future__ import annotations

import textwrap

from pfsense_shared.pfsense_parser import parse as parse_pfsense_xml
from pfsense_shared.pfsense_positions import build_positions


def _positions(xml: str) -> dict[str, tuple[int, int]]:
    """Fallback-mode positions — no parser output, emits only what
    lxml can see directly from the XML. Useful for testing individual
    elements in isolation; the production ``/parsed`` endpoint always
    passes ``parsed`` so the keys line up with the frontend."""
    return build_positions(textwrap.dedent(xml).strip().encode())


def _positions_with_parsed(xml: str) -> dict[str, tuple[int, int]]:
    """Production-mode positions: parse first, then build positions
    with the parsed config so firewall + NAT keys match the frontend."""
    blob = textwrap.dedent(xml).strip().encode()
    parsed = parse_pfsense_xml(blob)
    return build_positions(blob, parsed)


def test_firewall_rule_anchored_by_tracker():
    """``<filter><rule><tracker>X</tracker>…</rule>`` → ``xref-rule-X``.

    Matches ``rowAnchorId("rule", tracker)`` on the frontend — the
    hash deep-link target for every firewall row."""
    pos = _positions(
        """
        <pfsense>
          <filter>
            <rule>
              <tracker>1706288423</tracker>
              <type>pass</type>
            </rule>
          </filter>
        </pfsense>
        """
    )
    assert "xref-rule-1706288423" in pos
    start, end = pos["xref-rule-1706288423"]
    assert start >= 1
    assert end >= start


def test_firewall_rule_with_non_ident_tracker_sanitises_to_underscore():
    """Keys with ``:`` / ``/`` / ``|`` / ``.`` (rare but real —
    composite trackers on some downstream forks) must be sanitised
    via the same rule the frontend uses so the ids line up."""
    pos = _positions(
        """
        <pfsense>
          <filter>
            <rule>
              <tracker>fw:rule.42</tracker>
            </rule>
          </filter>
        </pfsense>
        """
    )
    assert "xref-rule-fw_rule_42" in pos


def test_nat_positions_with_parsed_emit_parser_keys():
    """v0.25.0 — when ``parsed`` is supplied, NAT rule positions
    pair lxml's document-order walk with the parser's ``nat_rules``
    list so keys match the frontend's
    ``rowAnchorId("nat", r.key)`` emission exactly."""
    import re

    xml = """
    <pfsense>
      <nat>
        <rule>
          <tracker>100</tracker>
          <interface>wan</interface>
          <target>10.0.0.5</target>
        </rule>
      </nat>
    </pfsense>
    """
    pos = _positions_with_parsed(xml)
    # Exactly one xref-nat-* anchor, keyed by the parser's
    # ``port_forward-...`` hash key (sanitised).
    nat_keys = [k for k in pos if k.startswith("xref-nat-")]
    assert len(nat_keys) == 1, nat_keys
    # Sanity: the key shape is ``xref-nat-hash_...``.
    assert re.match(r"^xref-nat-hash_[a-f0-9]{12}$", nat_keys[0])


def test_firewall_rule_with_parsed_uses_parser_key():
    """When ``parsed`` is supplied, firewall rule positions use the
    parser's ``r.key`` (``tracker:XXX`` / ``hash:...``) sanitised —
    matches the frontend's ``rowAnchorId("rule", r.key)`` emission."""
    xml = """
    <pfsense>
      <filter>
        <rule>
          <tracker>1706288423</tracker>
          <type>pass</type>
        </rule>
      </filter>
    </pfsense>
    """
    pos = _positions_with_parsed(xml)
    # With parsed, key is ``tracker:1706288423`` → sanitised
    # ``tracker_1706288423``.
    assert "xref-rule-tracker_1706288423" in pos


def test_kind_anchors_cover_every_refkind():
    """One positive assertion per RefKind so drift on either side
    between frontend and backend is caught at test time."""
    pos = _positions(
        """
        <pfsense>
          <aliases>
            <alias><name>RFC1918</name></alias>
          </aliases>
          <gateways>
            <gateway_item><name>WAN_DHCP</name></gateway_item>
            <gateway_group><name>WAN_FAILOVER</name></gateway_group>
          </gateways>
          <schedules>
            <schedule><name>Weekends</name></schedule>
          </schedules>
          <ca><refid>ca_abc</refid></ca>
          <cert><refid>cert_abc</refid></cert>
          <crl><refid>crl_abc</refid></crl>
          <system>
            <authserver><name>ldap-corp</name></authserver>
            <user><name>admin</name></user>
            <group><name>admins</name></group>
          </system>
          <openvpn>
            <openvpn-server><vpnid>1</vpnid></openvpn-server>
            <openvpn-client><vpnid>2</vpnid></openvpn-client>
          </openvpn>
          <ipsec>
            <phase1><ikeid>1</ikeid></phase1>
          </ipsec>
          <load_balancer>
            <lbpool><name>web-pool</name></lbpool>
          </load_balancer>
          <vlans>
            <vlan><vlanif>em0.100</vlanif></vlan>
          </vlans>
          <ifgroups>
            <ifgroupentry><ifname>VPN</ifname></ifgroupentry>
          </ifgroups>
          <interfaces>
            <wan/>
            <lan/>
            <opt1/>
          </interfaces>
        </pfsense>
        """
    )
    for want in (
        "xref-alias-RFC1918",
        "xref-gateway-WAN_DHCP",
        "xref-gateway_group-WAN_FAILOVER",
        "xref-schedule-Weekends",
        "xref-ca-ca_abc",
        "xref-cert-cert_abc",
        "xref-crl-crl_abc",
        "xref-authserver-ldap-corp",
        "xref-user-admin",
        "xref-group-admins",
        "xref-openvpn_server-1",
        "xref-openvpn_client-2",
        "xref-ipsec_phase1-1",
        "xref-lb_pool-web-pool",
        "xref-vlan-em0_100",
        "xref-interface_group-VPN",
        "xref-interface-wan",
        "xref-interface-lan",
        "xref-interface-opt1",
    ):
        assert want in pos, f"missing {want}"


def test_singleton_fields_and_section_anchors():
    """Singleton sections (System, DNS, NTP, …) render as a Dl in the
    viewer; each ``<dt>`` gets ``id="field-{section}-{fieldname}"`` so
    intersection tracking can pinpoint the row the user is reading.
    Backend must emit matching keys."""
    pos = _positions(
        """
        <pfsense>
          <system>
            <hostname>pfs01</hostname>
            <domain>example.com</domain>
            <timezone>UTC</timezone>
          </system>
          <dnsmasq>
            <enable>on</enable>
            <interface>lan</interface>
          </dnsmasq>
          <ntpd>
            <interface>wan</interface>
          </ntpd>
        </pfsense>
        """
    )
    # Section-level fallback anchors.
    assert "section-system" in pos
    assert "section-dns" in pos
    assert "section-ntpd" in pos
    # Field-level — every direct child of the singleton.
    for want in (
        "field-system-hostname",
        "field-system-domain",
        "field-system-timezone",
        "field-dns-enable",
        "field-dns-interface",
        "field-ntpd-interface",
    ):
        assert want in pos, f"missing {want}"


def test_installed_packages_singleton_sections():
    """Package-level singletons (Avahi, miniUPnPd, OpenVPN-export,
    Telegraf) share the positions-map contract — their fields need
    ``field-{section}-{fieldname}`` too."""
    pos = _positions(
        """
        <pfsense>
          <installedpackages>
            <avahi>
              <enable>on</enable>
              <enable_ipv4>on</enable_ipv4>
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
    )
    for want in (
        "field-avahi-enable",
        "field-avahi-enable_ipv4",
        "field-miniupnpd-enable_upnp",
        "field-telegraf-url",
    ):
        assert want in pos, f"missing {want}"


def test_line_ranges_are_1_based_and_monotonic():
    """Monaco uses 1-based lines. Start line must equal the element's
    opening-tag line; end must be ≥ start so the reverse lookup
    (cursor-line → enclosing anchor) can use inclusive bracket math."""
    xml = (
        "<pfsense>\n"           # line 1
        "  <system>\n"          # line 2
        "    <hostname>x</hostname>\n"  # line 3
        "    <domain>ex</domain>\n"     # line 4
        "  </system>\n"         # line 5
        "</pfsense>\n"          # line 6
    )
    pos = build_positions(xml.encode())
    h_start, h_end = pos["field-system-hostname"]
    assert h_start == 3
    assert h_end >= h_start
    s_start, _ = pos["section-system"]
    assert s_start == 2


def test_positions_and_scopes_tables_stay_in_sync():
    """Drift-resistance, both directions: every ``_KIND_ANCHORS``
    kind in positions.py must also resolve via ``_ROW_SCOPES`` in
    anchor_values.py, and every ``_ROW_SCOPES`` entry must have a
    corresponding positions emitter so the blame drawer and the
    tab-switch always agree on which anchors are reachable.

    Adding a resolver scope without a matching positions entry
    produces silent tab-switch misses — the blame drawer resolves
    the anchor but the Raw XML tab can't find it. Adding a positions
    entry without a resolver scope produces silent blame-drawer
    misses — the Raw XML tab scrolls correctly but the history
    drawer returns None for every backup."""
    from pfsense_shared import pfsense_anchor_values as av
    from pfsense_shared import pfsense_positions as pp

    # Positions side: every kind emitted as an anchor.
    pos_kinds = {kind for kind, _, _ in pp._KIND_ANCHORS}
    # ``interface`` is handled by ``_interface_anchors`` (element
    # tag, not xpath+key_tag), so it's not in ``_KIND_ANCHORS`` but
    # IS in ``_ROW_SCOPES``. Add it so the assertion is symmetric.
    pos_kinds.add("interface")
    # Firewall + NAT rules aren't in ``_KIND_ANCHORS`` either (they
    # go through ``_firewall_and_nat_anchors``); their scopes are
    # ``rule`` / ``nat`` in ``_ROW_SCOPES``.
    pos_kinds.update({"rule", "nat"})

    scope_kinds = set(av._ROW_SCOPES.keys())

    missing_scope = pos_kinds - scope_kinds
    assert not missing_scope, (
        f"positions emit anchor kinds with no resolver scope: "
        f"{missing_scope}"
    )

    missing_positions = scope_kinds - pos_kinds
    assert not missing_positions, (
        f"resolver scopes with no matching positions emitter: "
        f"{missing_positions} — adding a _ROW_SCOPES entry without "
        f"also adding to _KIND_ANCHORS (or _interface_anchors / "
        f"_firewall_and_nat_anchors) means the blame drawer can "
        f"resolve an anchor the Raw XML tab-switch can't find"
    )

    # Every singleton section emitted as ``section-{name}`` /
    # ``field-{name}-*`` resolves via ``_SINGLETON_PATH``.
    pos_singletons = {name for name, _, _ in pp._SINGLETON_SECTIONS}
    path_singletons = set(av._SINGLETON_PATH.keys())
    missing_path = pos_singletons - path_singletons
    assert not missing_path, (
        f"singleton sections emitted by positions with no "
        f"_SINGLETON_PATH entry: {missing_path}"
    )
    # Reverse direction for singletons too.
    missing_pos_singletons = path_singletons - pos_singletons
    assert not missing_pos_singletons, (
        f"_SINGLETON_PATH entries with no matching "
        f"_SINGLETON_SECTIONS emitter: {missing_pos_singletons}"
    )


def test_missing_key_skips_row():
    """Rows without a tracker / refid / name can't produce a stable
    anchor — they're skipped rather than emitted with an empty key."""
    pos = _positions(
        """
        <pfsense>
          <filter>
            <rule>
              <type>pass</type>
            </rule>
          </filter>
          <aliases>
            <alias>
              <descr>no name</descr>
            </alias>
          </aliases>
        </pfsense>
        """
    )
    # No firewall or alias anchors emitted.
    assert not any(k.startswith("xref-rule-") for k in pos)
    assert not any(k.startswith("xref-alias-") for k in pos)
