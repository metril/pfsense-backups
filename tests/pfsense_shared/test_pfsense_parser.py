"""Parser tests — one assertion block per section.

Fixture: ``fixtures/sample_config_v0_11_0.xml`` covers every section
implemented in the v0.11.0 phase with 1–2 representative items. The
fixture is intentionally small so these tests read as documentation
for what the parser extracts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pfsense_shared.pfsense_parser import ParsedConfig, parse
from pfsense_shared.pfsense_redact import REDACTED

FIXTURE = Path(__file__).parent / "fixtures" / "sample_config_v0_11_0.xml"


@pytest.fixture(scope="module")
def parsed() -> ParsedConfig:
    return parse(FIXTURE.read_bytes())


def test_empty_bytes_returns_empty_config() -> None:
    out = parse(b"")
    assert out == ParsedConfig()


def test_config_version(parsed: ParsedConfig) -> None:
    assert parsed.config_version == "21.9"


def test_system(parsed: ParsedConfig) -> None:
    assert parsed.system is not None
    s = parsed.system
    assert s.hostname == "gw"
    assert s.domain == "lan.example"
    assert s.timezone == "UTC"
    assert s.timeservers == ["0.pool.ntp.org", "1.pool.ntp.org"]
    assert s.dnsservers == ["1.1.1.1", "9.9.9.9"]
    assert s.dns_allow_override is True
    assert s.webgui is not None
    assert s.webgui.protocol == "https"
    assert s.webgui.port == "443"
    assert s.enablesshd is True
    assert s.sshport == "22"


def test_revision(parsed: ParsedConfig) -> None:
    assert parsed.revision is not None
    r = parsed.revision
    assert r.description == "initial"
    assert r.username == "admin@127.0.0.1"
    assert r.time is not None  # datetime present


def test_sysctl(parsed: ParsedConfig) -> None:
    assert len(parsed.sysctl) == 1
    assert parsed.sysctl[0].tunable == "net.inet.ip.random_id"
    assert parsed.sysctl[0].value == "1"


def test_cron(parsed: ParsedConfig) -> None:
    assert len(parsed.cron) == 1
    assert parsed.cron[0].who == "root"
    assert "rc.filter_configure" in (parsed.cron[0].command or "")


def test_interfaces(parsed: ParsedConfig) -> None:
    keys = [i.key for i in parsed.interfaces]
    assert keys == ["wan", "lan", "opt1"]
    wan = parsed.interfaces[0]
    assert wan.if_ == "em0"
    assert wan.ipaddr == "dhcp"
    assert wan.blockpriv is True
    assert wan.blockbogons is True
    assert wan.enabled is True


def test_gateways(parsed: ParsedConfig) -> None:
    assert len(parsed.gateways) == 1
    gw = parsed.gateways[0]
    assert gw.name == "WAN_DHCP"
    assert gw.defaultgw is True


def test_static_routes(parsed: ParsedConfig) -> None:
    assert len(parsed.static_routes) == 1
    r = parsed.static_routes[0]
    assert r.network == "192.168.99.0/24"
    assert r.gateway == "WAN_DHCP"


def test_firewall_rules(parsed: ParsedConfig) -> None:
    assert len(parsed.firewall_rules) == 2
    allow = parsed.firewall_rules[0]
    assert allow.key.startswith("tracker:")
    assert allow.type == "pass"
    assert allow.interface == "lan"
    assert allow.source.network == "lan"
    assert allow.destination.any_ is True
    deny = parsed.firewall_rules[1]
    assert deny.type == "block"
    assert deny.log is True


def test_nat_rules(parsed: ParsedConfig) -> None:
    kinds = {r.kind for r in parsed.nat_rules}
    assert kinds == {"port_forward", "outbound"}
    pf = next(r for r in parsed.nat_rules if r.kind == "port_forward")
    assert pf.target == "192.168.1.10"
    assert pf.local_port == "443"


def test_nat_key_stable_across_description_edits() -> None:
    """Regression: NAT rule keys must NOT change when only the
    ``<descr>`` is edited. v0.40.0 removed descr from the key
    derivation — otherwise every description tweak forces a bogus
    add+remove pair in the anchor-event log, polluting blame."""
    from pfsense_shared.pfsense_parser import parse

    base = b"""<pfsense><nat>
      <rule>
        <interface>wan</interface>
        <protocol>tcp</protocol>
        <target>192.0.2.10</target>
        <local-port>443</local-port>
        <descr>original description</descr>
        <destination><port>443</port></destination>
      </rule>
    </nat></pfsense>"""
    edited = b"""<pfsense><nat>
      <rule>
        <interface>wan</interface>
        <protocol>tcp</protocol>
        <target>192.0.2.10</target>
        <local-port>443</local-port>
        <descr>edited description</descr>
        <destination><port>443</port></destination>
      </rule>
    </nat></pfsense>"""
    k1 = parse(base).nat_rules[0].key
    k2 = parse(edited).nat_rules[0].key
    assert k1 == k2, (
        f"NAT key shouldn't change on description edits; got {k1!r} -> {k2!r}"
    )


def test_nat_key_changes_on_target_edit() -> None:
    """Contrapositive: when a functionally-significant field (target
    IP, port, interface, protocol) changes, the NAT key MUST change
    so the projector emits an add+remove pair — a rule retargeted
    to a different internal host is effectively a new rule."""
    from pfsense_shared.pfsense_parser import parse

    base = b"""<pfsense><nat>
      <rule>
        <interface>wan</interface>
        <target>192.0.2.10</target>
        <local-port>443</local-port>
      </rule>
    </nat></pfsense>"""
    retargeted = b"""<pfsense><nat>
      <rule>
        <interface>wan</interface>
        <target>192.0.2.11</target>
        <local-port>443</local-port>
      </rule>
    </nat></pfsense>"""
    k1 = parse(base).nat_rules[0].key
    k2 = parse(retargeted).nat_rules[0].key
    assert k1 != k2, (
        f"NAT key should change on target edits; got {k1!r} for both"
    )


def test_filter_key_stable_across_description_edits() -> None:
    """Regression: firewall rule keys must NOT change when only the
    ``<descr>`` is edited. v0.41.0 ported the NAT content-hash
    pattern — the pre-tracker fallback used to include ``<descr>``,
    which forked blame on every description tweak. Modern configs
    use ``<tracker>`` and skip the fallback entirely; this test
    exercises the fallback by omitting the tracker."""
    from pfsense_shared.pfsense_parser import parse

    base = b"""<pfsense><filter>
      <rule>
        <type>pass</type>
        <interface>lan</interface>
        <ipprotocol>inet</ipprotocol>
        <protocol>tcp</protocol>
        <source><network>lan</network></source>
        <destination><any/></destination>
        <descr>original description</descr>
      </rule>
    </filter></pfsense>"""
    edited = b"""<pfsense><filter>
      <rule>
        <type>pass</type>
        <interface>lan</interface>
        <ipprotocol>inet</ipprotocol>
        <protocol>tcp</protocol>
        <source><network>lan</network></source>
        <destination><any/></destination>
        <descr>edited description</descr>
      </rule>
    </filter></pfsense>"""
    k1 = parse(base).firewall_rules[0].key
    k2 = parse(edited).firewall_rules[0].key
    assert k1.startswith("hash:"), f"fallback path should produce hash key; got {k1!r}"
    assert k1 == k2, (
        f"filter key shouldn't change on description edits; got {k1!r} -> {k2!r}"
    )


def test_filter_key_changes_on_interface_edit() -> None:
    """Contrapositive: moving the rule to a different interface DOES
    change the fallback key — that's a functionally different rule,
    not a cosmetic edit."""
    from pfsense_shared.pfsense_parser import parse

    base = b"""<pfsense><filter>
      <rule>
        <type>pass</type>
        <interface>lan</interface>
        <ipprotocol>inet</ipprotocol>
        <protocol>tcp</protocol>
      </rule>
    </filter></pfsense>"""
    moved = b"""<pfsense><filter>
      <rule>
        <type>pass</type>
        <interface>opt1</interface>
        <ipprotocol>inet</ipprotocol>
        <protocol>tcp</protocol>
      </rule>
    </filter></pfsense>"""
    k1 = parse(base).firewall_rules[0].key
    k2 = parse(moved).firewall_rules[0].key
    assert k1 != k2, f"filter key should change on interface edits; got {k1!r} for both"


def test_filter_key_changes_on_floating_toggle() -> None:
    """Flipping a rule from per-interface to floating changes its
    evaluation order / semantics. The key MUST change so blame
    shows remove+add rather than silently merging two distinct
    rulesets into one anchor."""
    from pfsense_shared.pfsense_parser import parse

    per_iface = b"""<pfsense><filter>
      <rule>
        <type>pass</type>
        <interface>lan</interface>
        <ipprotocol>inet</ipprotocol>
        <protocol>tcp</protocol>
      </rule>
    </filter></pfsense>"""
    floating = b"""<pfsense><filter>
      <rule>
        <type>pass</type>
        <interface>lan</interface>
        <ipprotocol>inet</ipprotocol>
        <protocol>tcp</protocol>
        <floating>yes</floating>
        <direction>any</direction>
      </rule>
    </filter></pfsense>"""
    k1 = parse(per_iface).firewall_rules[0].key
    k2 = parse(floating).firewall_rules[0].key
    assert k1 != k2, f"filter key should change on floating toggle; got {k1!r} for both"


def test_filter_key_changes_on_statetype_edit() -> None:
    """``<statetype>`` drives pf's state-tracking behaviour —
    ``keep state`` vs ``none`` vs ``synproxy`` are functionally
    different rules even when everything else matches."""
    from pfsense_shared.pfsense_parser import parse

    base = b"""<pfsense><filter>
      <rule>
        <type>pass</type>
        <interface>lan</interface>
        <ipprotocol>inet</ipprotocol>
        <protocol>tcp</protocol>
        <statetype>keep state</statetype>
      </rule>
    </filter></pfsense>"""
    flipped = b"""<pfsense><filter>
      <rule>
        <type>pass</type>
        <interface>lan</interface>
        <ipprotocol>inet</ipprotocol>
        <protocol>tcp</protocol>
        <statetype>none</statetype>
      </rule>
    </filter></pfsense>"""
    k1 = parse(base).firewall_rules[0].key
    k2 = parse(flipped).firewall_rules[0].key
    assert k1 != k2, f"filter key should change on statetype flip; got {k1!r} for both"


def test_aliases(parsed: ParsedConfig) -> None:
    names = [a.name for a in parsed.aliases]
    assert names == ["WEB_PORTS", "MGMT_HOSTS"]
    web = parsed.aliases[0]
    assert web.entries == ["80", "443", "8443"]
    assert web.details == ["http", "https", "alt"]


def test_dhcp_servers(parsed: ParsedConfig) -> None:
    assert len(parsed.dhcp_servers) == 1
    lan = parsed.dhcp_servers[0]
    assert lan.interface == "lan"
    assert lan.range_from == "192.168.1.100"
    assert lan.range_to == "192.168.1.200"
    assert len(lan.static_mappings) == 1
    assert lan.static_mappings[0].mac == "00:11:22:33:44:55"


def test_dns(parsed: ParsedConfig) -> None:
    assert parsed.dns is not None
    assert parsed.dns.unbound_enabled is True
    assert parsed.dns.dnsmasq_enabled is False
    assert len(parsed.dns.host_overrides) == 1
    assert parsed.dns.host_overrides[0].host == "app"
    assert len(parsed.dns.domain_overrides) == 1
    assert parsed.dns.domain_overrides[0].domain == "corp.internal"


def test_users(parsed: ParsedConfig) -> None:
    names = [u.name for u in parsed.users]
    assert names == ["admin", "alice"]
    admin = parsed.users[0]
    # Redaction: bcrypt hash must not leak through.
    assert admin.bcrypt_hash == REDACTED
    assert admin.groups == ["admins"]
    assert admin.certrefs == ["cert-refid-1"]


def test_groups(parsed: ParsedConfig) -> None:
    names = [g.name for g in parsed.groups]
    assert names == ["admins", "ops"]
    assert parsed.groups[0].privs == ["page-all"]
    assert parsed.groups[0].members == ["0"]


def test_authservers(parsed: ParsedConfig) -> None:
    assert len(parsed.authservers) == 1
    a = parsed.authservers[0]
    assert a.type == "ldap"
    assert a.host == "ldap.lan.example"
    assert a.port == "636"
    assert a.ldap_bindpw == REDACTED
    assert a.ldap_binddn == "cn=bind,dc=lan,dc=example"


def test_unrecognized_sections_excludes_known_and_ignored(
    parsed: ParsedConfig,
) -> None:
    tags = [s.tag for s in parsed.unrecognized_sections]
    # widgets is ignored; hasync is known-planned (placeholder until v0.11.1).
    # Neither should appear in the unrecognized list.
    assert "widgets" not in tags
    assert "hasync" not in tags


def test_no_secret_values_anywhere_in_parsed_output(
    parsed: ParsedConfig,
) -> None:
    """Defense in depth: round-trip to JSON and check no known-secret
    strings appear. Catches a future section parser that forgets to
    redact a field."""
    blob = parsed.model_dump_json()
    for secret in ("SECRETHASH", "ALICESECRET", "supersecret"):
        assert secret not in blob, f"{secret!r} leaked into parsed output"
