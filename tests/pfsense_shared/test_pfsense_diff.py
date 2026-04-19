"""Diff-engine tests — added / removed / modified / reordered per section.

Uses small per-test XML snippets rather than the big shared fixture so
the interesting change is obvious on the page.
"""

from __future__ import annotations

import textwrap

from pfsense_shared.pfsense_diff import diff_configs
from pfsense_shared.pfsense_parser import parse


def _parse(xml: str) -> object:
    return parse(textwrap.dedent(xml).strip().encode())


def test_identical_configs_report_no_changes() -> None:
    xml = """\
    <pfsense>
      <version>21.9</version>
      <system><hostname>h</hostname></system>
      <filter>
        <rule><tracker>1</tracker><type>pass</type><interface>lan</interface><descr>r1</descr></rule>
      </filter>
    </pfsense>
    """
    a = _parse(xml)
    b = _parse(xml)
    d = diff_configs(a, b)  # type: ignore[arg-type]
    assert d.system.is_empty
    assert d.firewall_rules.is_empty
    assert d.aliases.is_empty
    assert d.firewall_rules.unchanged_count == 1


def test_firewall_add_remove_modify() -> None:
    a = _parse("""
        <pfsense>
          <filter>
            <rule><tracker>1</tracker><type>pass</type><interface>lan</interface><descr>r1</descr></rule>
            <rule><tracker>2</tracker><type>pass</type><interface>lan</interface><descr>r2</descr></rule>
          </filter>
        </pfsense>
    """)
    b = _parse(
        "<pfsense><filter>"
        "<rule><tracker>1</tracker><type>pass</type><interface>lan</interface>"
        "<descr>r1 edited</descr></rule>"
        "<rule><tracker>3</tracker><type>block</type><interface>wan</interface>"
        "<descr>r3 new</descr></rule>"
        "</filter></pfsense>"
    )
    d = diff_configs(a, b)  # type: ignore[arg-type]
    assert [x["descr"] for x in d.firewall_rules.added] == ["r3 new"]
    assert [x["descr"] for x in d.firewall_rules.removed] == ["r2"]
    assert len(d.firewall_rules.modified) == 1
    m = d.firewall_rules.modified[0]
    assert m.key == "tracker:1"
    assert any(c.field == "descr" for c in m.changes)


def test_firewall_reorder_is_flagged() -> None:
    a = _parse("""
        <pfsense>
          <filter>
            <rule><tracker>1</tracker><type>pass</type><interface>lan</interface></rule>
            <rule><tracker>2</tracker><type>pass</type><interface>lan</interface></rule>
          </filter>
        </pfsense>
    """)
    b = _parse("""
        <pfsense>
          <filter>
            <rule><tracker>2</tracker><type>pass</type><interface>lan</interface></rule>
            <rule><tracker>1</tracker><type>pass</type><interface>lan</interface></rule>
          </filter>
        </pfsense>
    """)
    d = diff_configs(a, b)  # type: ignore[arg-type]
    keys = sorted(r.key for r in d.firewall_rules.reordered)
    assert keys == ["tracker:1", "tracker:2"]


def test_system_scalar_change() -> None:
    a = _parse("<pfsense><system><hostname>old</hostname></system></pfsense>")
    b = _parse("<pfsense><system><hostname>new</hostname></system></pfsense>")
    d = diff_configs(a, b)  # type: ignore[arg-type]
    assert len(d.system.modified) == 1
    changes = d.system.modified[0].changes
    hostname = next(c for c in changes if c.field == "hostname")
    assert hostname.before == "old"
    assert hostname.after == "new"


def test_aliases_entries_change() -> None:
    a = _parse(
        "<pfsense><aliases><alias><name>WEB</name><type>port</type>"
        "<address>80 443</address></alias></aliases></pfsense>"
    )
    b = _parse(
        "<pfsense><aliases><alias><name>WEB</name><type>port</type>"
        "<address>80 443 8443</address></alias></aliases></pfsense>"
    )
    d = diff_configs(a, b)  # type: ignore[arg-type]
    assert len(d.aliases.modified) == 1
    c = d.aliases.modified[0].changes[0]
    assert c.field == "entries"
    assert c.before == ["80", "443"]
    assert c.after == ["80", "443", "8443"]


def test_optional_dns_added() -> None:
    a = _parse("<pfsense></pfsense>")
    b = _parse("<pfsense><unbound><enable/><port>53</port></unbound></pfsense>")
    d = diff_configs(a, b)  # type: ignore[arg-type]
    assert len(d.dns.added) == 1
    assert d.dns.added[0]["unbound_enabled"] is True


def test_optional_dns_removed() -> None:
    a = _parse("<pfsense><unbound><enable/></unbound></pfsense>")
    b = _parse("<pfsense></pfsense>")
    d = diff_configs(a, b)  # type: ignore[arg-type]
    assert len(d.dns.removed) == 1


def test_config_version_scalar_diff() -> None:
    a = _parse("<pfsense><version>21.9</version></pfsense>")
    b = _parse("<pfsense><version>22.0</version></pfsense>")
    d = diff_configs(a, b)  # type: ignore[arg-type]
    assert len(d.config_version.modified) == 1
    c = d.config_version.modified[0].changes[0]
    assert c.before == "21.9"
    assert c.after == "22.0"
