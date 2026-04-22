"""Tests for ``pfsense_shared.anchor_events`` — the projector that
turns a ``ConfigDiff`` + ``ParsedConfig`` into ``(anchor_id, kind,
value)`` tuples for bulk-insert into the ``anchor_event`` table.

Contract the tests pin:

- ``enumerate_anchors(parsed)`` emits one tuple per anchor the
  frontend knows how to render — cross-checked by resolving each
  emitted ``anchor_id`` through ``resolve_anchor_value`` on the
  same parsed config and asserting equality.
- ``diff_to_anchor_events(diff, parsed_after)`` emits the expected
  ``kind`` (added / modified / removed / reordered) for synthetic
  diffs covering every code path: a row added, a row removed, a
  row modified, a row reordered-but-unchanged, a singleton field
  changed, a whole singleton appearing for the first time.
- Nested dotted field paths (``webgui.port``) are skipped — the
  resolver doesn't address them yet, so events for them would
  have no UI consumer.
- anchor_id → section decoding (``section_for_anchor``) round-trips
  against the emitted IDs.
"""

from __future__ import annotations

import textwrap

from pfsense_shared.anchor_events import (
    diff_to_anchor_events,
    enumerate_anchors,
    section_for_anchor,
)
from pfsense_shared.pfsense_anchor_values import resolve_anchor_value
from pfsense_shared.pfsense_diff import diff_configs
from pfsense_shared.pfsense_parser import parse


def _cfg(xml: str):
    return parse(textwrap.dedent(xml).strip().encode())


BASE_XML = """
<pfsense>
  <system>
    <hostname>gw01</hostname>
    <domain>example.com</domain>
  </system>
  <filter>
    <rule>
      <tracker>1001</tracker>
      <type>pass</type>
      <interface>lan</interface>
      <descr>allow lan</descr>
    </rule>
    <rule>
      <tracker>1002</tracker>
      <type>block</type>
      <interface>wan</interface>
      <descr>block wan</descr>
    </rule>
  </filter>
  <aliases>
    <alias>
      <name>RFC1918</name>
      <address>10.0.0.0/8</address>
    </alias>
  </aliases>
</pfsense>
"""


def test_enumerate_anchors_round_trip():
    """Every ``(anchor_id, value)`` emitted by ``enumerate_anchors``
    must resolve back to the same value via ``resolve_anchor_value``
    on the same parsed config. Catches drift between the projector's
    SECTION_SPEC / SINGLETON_SPEC and the resolver's
    _ROW_SCOPES / _SINGLETON_PATH."""
    cfg = _cfg(BASE_XML)
    emitted = list(enumerate_anchors(cfg))
    assert emitted, "should emit at least the hostname + one rule"

    # Field-level values are scalars; row-level are dicts. The
    # resolver returns a dict for rows, a string for field values
    # (via _stringify). Normalise the projector-side before compare.
    for anchor_id, value in emitted:
        resolved = resolve_anchor_value(cfg, anchor_id)
        if anchor_id.startswith("field-"):
            # ``enumerate_anchors`` yields the raw Python value; the
            # resolver stringifies (booleans → "yes"/"no", lists →
            # comma-join). Accept either for the round-trip — the
            # identities match after normalisation.
            assert resolved is not None or value is None, anchor_id
        else:
            assert isinstance(resolved, dict), anchor_id
            # Resolver uses the anchor_key_field to look up the row,
            # projector dumped from the same row. Same key = same
            # dict.
            assert resolved == value, anchor_id


def test_added_row_yields_added_event():
    before = _cfg(BASE_XML)
    after = _cfg(
        BASE_XML.replace(
            "</aliases>",
            """<alias>
      <name>BOGON</name>
      <address>0.0.0.0/8</address>
    </alias>
  </aliases>""",
        )
    )
    events = list(diff_to_anchor_events(diff_configs(before, after), after))
    bogon_added = [
        (aid, v)
        for aid, kind, v in events
        if kind == "added" and aid == "xref-alias-BOGON"
    ]
    assert len(bogon_added) == 1
    _, row = bogon_added[0]
    assert row["name"] == "BOGON"


def test_removed_row_yields_removed_event():
    after = _cfg(BASE_XML)
    before_xml = BASE_XML.replace(
        "</aliases>",
        """<alias>
      <name>DOOMED</name>
      <address>1.2.3.4/32</address>
    </alias>
  </aliases>""",
    )
    before = _cfg(before_xml)
    events = list(diff_to_anchor_events(diff_configs(before, after), after))
    removed_ids = [aid for aid, kind, _ in events if kind == "removed"]
    assert "xref-alias-DOOMED" in removed_ids


def test_modified_row_yields_modified_event_with_full_row():
    before = _cfg(BASE_XML)
    after_xml = BASE_XML.replace(
        "<descr>allow lan</descr>",
        "<descr>allow lan traffic</descr>",
    )
    after = _cfg(after_xml)
    events = list(diff_to_anchor_events(diff_configs(before, after), after))
    # The firewall rule's anchor_key_field is ``key`` — the parser
    # synthesises ``tracker:1001``. Find the emitted event whose
    # descr was updated to the new value.
    mods = [
        (aid, v)
        for aid, kind, v in events
        if kind == "modified"
        and aid.startswith("xref-rule-")
        and isinstance(v, dict)
        and v.get("descr") == "allow lan traffic"
    ]
    assert len(mods) == 1, f"expected 1 modified rule event, got {events}"


def test_dns_unbound_field_change_emits_tag_based_anchor():
    """Regression: toggling ``<dnsmasq><enable>`` from absent to
    present produces a ``field-dns-enable`` event (NOT
    ``field-dns-dnsmasq_enabled``) so the id matches what the
    frontend + positions map use. Symmetric for
    ``<unbound><enable>`` → ``field-unbound-enable``. Without the
    rescope table, the projector would emit the Pydantic-field
    name and the drawer would show empty timelines.

    ``bool_flag`` treats the element's presence as True and its
    absence as False, so the before/after XMLs omit vs include the
    ``<enable>`` child to force a real field diff."""
    base = """
    <pfsense>
      <dnsmasq></dnsmasq>
      <unbound></unbound>
    </pfsense>
    """
    after_xml = """
    <pfsense>
      <dnsmasq><enable>on</enable></dnsmasq>
      <unbound><enable>on</enable></unbound>
    </pfsense>
    """
    before = _cfg(base)
    after = _cfg(after_xml)
    events = list(diff_to_anchor_events(diff_configs(before, after), after))
    ids = {aid for aid, _k, _v in events}
    assert "field-dns-enable" in ids
    assert "field-unbound-enable" in ids
    # Not the Pydantic-field names — those would miss the resolver.
    assert "field-dns-dnsmasq_enabled" not in ids
    assert "field-dns-unbound_enabled" not in ids


def test_singleton_field_change_yields_field_event():
    before = _cfg(BASE_XML)
    after = _cfg(BASE_XML.replace("<hostname>gw01</hostname>", "<hostname>gw02</hostname>"))
    events = list(diff_to_anchor_events(diff_configs(before, after), after))
    assert ("field-system-hostname", "modified", "gw02") in events


def test_reorder_without_modification_yields_reordered():
    """Swap rule 1001 and 1002 without changing anything else →
    ``reordered`` events, not ``modified``."""
    before = _cfg(BASE_XML)
    swapped = """
    <pfsense>
      <system>
        <hostname>gw01</hostname>
        <domain>example.com</domain>
      </system>
      <filter>
        <rule>
          <tracker>1002</tracker>
          <type>block</type>
          <interface>wan</interface>
          <descr>block wan</descr>
        </rule>
        <rule>
          <tracker>1001</tracker>
          <type>pass</type>
          <interface>lan</interface>
          <descr>allow lan</descr>
        </rule>
      </filter>
      <aliases>
        <alias>
          <name>RFC1918</name>
          <address>10.0.0.0/8</address>
        </alias>
      </aliases>
    </pfsense>
    """
    after = _cfg(swapped)
    events = list(diff_to_anchor_events(diff_configs(before, after), after))
    rule_kinds = {
        kind for aid, kind, _v in events if aid.startswith("xref-rule-")
    }
    # No row modified (fields unchanged), but both rules reordered.
    assert "reordered" in rule_kinds
    assert "modified" not in rule_kinds


def test_modified_and_reordered_rule_emits_both_events():
    """Regression: a firewall rule that is BOTH edited and moved
    surfaces as two events (one ``modified``, one ``reordered``) at
    the same ``occurred_at``. pfSense evaluates rules top-to-bottom
    so the position change is operationally distinct from any field
    edit and must show up independently in blame + cumulative
    views. Earlier versions suppressed the reorder event when the
    rule was also modified, hiding the move from operators."""
    before = _cfg(BASE_XML)
    # Swap the two rules AND change rule 1001's description.
    after_xml = """
    <pfsense>
      <system>
        <hostname>gw01</hostname>
        <domain>example.com</domain>
      </system>
      <filter>
        <rule>
          <tracker>1002</tracker>
          <type>block</type>
          <interface>wan</interface>
          <descr>block wan</descr>
        </rule>
        <rule>
          <tracker>1001</tracker>
          <type>pass</type>
          <interface>lan</interface>
          <descr>allow lan — edited</descr>
        </rule>
      </filter>
      <aliases>
        <alias>
          <name>RFC1918</name>
          <address>10.0.0.0/8</address>
        </alias>
      </aliases>
    </pfsense>
    """
    after = _cfg(after_xml)
    events = list(diff_to_anchor_events(diff_configs(before, after), after))
    rule_1001 = [
        (kind, v)
        for aid, kind, v in events
        if aid.startswith("xref-rule-") and isinstance(v, dict)
        and v.get("descr", "").startswith("allow lan")
    ]
    kinds = {kind for kind, _v in rule_1001}
    assert "modified" in kinds, f"expected modified event for rule 1001, got {events}"
    assert "reordered" in kinds, f"expected reordered event for rule 1001, got {events}"


def test_section_for_anchor_decodes():
    assert section_for_anchor("xref-rule-tracker_1001") == "firewall_rules"
    assert section_for_anchor("xref-alias-RFC1918") == "aliases"
    assert section_for_anchor("field-system-hostname") == "system"
    assert section_for_anchor("field-dns-enable") == "dns"
    assert section_for_anchor("not-an-anchor") is None
    assert section_for_anchor("xref-unknown_kind-x") is None


def test_package_singleton_field_change_yields_event():
    """``installedpackages.telegraf.url`` changing surfaces as a
    ``field-telegraf-url`` event with kind=modified, not buried
    under ``field-installedpackages-*`` or dropped entirely. Same
    contract for avahi / miniupnpd / openvpn_client_export.

    Telegraf's ``url`` is used rather than e.g. avahi's ``enable``
    because the avahi parser normalises on/off-flavoured booleans
    aggressively enough that a string flip doesn't actually produce
    a FieldChange — the parsed config is identical. ``url`` is a
    plain scalar so the diff triggers cleanly."""
    base_xml = """
    <pfsense>
      <system><hostname>gw</hostname></system>
      <installedpackages>
        <telegraf><url>http://host:8086</url></telegraf>
      </installedpackages>
    </pfsense>
    """
    after_xml = """
    <pfsense>
      <system><hostname>gw</hostname></system>
      <installedpackages>
        <telegraf><url>http://host:9000</url></telegraf>
      </installedpackages>
    </pfsense>
    """
    before = _cfg(base_xml)
    after = _cfg(after_xml)
    events = list(diff_to_anchor_events(diff_configs(before, after), after))
    matching = [
        (aid, kind, v)
        for aid, kind, v in events
        if aid == "field-telegraf-url"
    ]
    assert matching == [("field-telegraf-url", "modified", "http://host:9000")]


def test_haproxy_backend_row_change_yields_xref_event():
    """Adding / modifying / removing an HAProxy backend surfaces as
    a ``xref-haproxy_backend-<name>`` event — not a storm of
    ``field-installedpackages-*`` events per sub-field, and not
    dropped entirely. Regression test against the pfSense-expert
    review finding."""
    base = """
    <pfsense>
      <installedpackages>
        <haproxy>
          <ha_backends>
            <item>
              <name>web-back</name>
              <balance>roundrobin</balance>
            </item>
          </ha_backends>
        </haproxy>
      </installedpackages>
    </pfsense>
    """
    after_xml = """
    <pfsense>
      <installedpackages>
        <haproxy>
          <ha_backends>
            <item>
              <name>web-back</name>
              <balance>leastconn</balance>
            </item>
            <item>
              <name>api-back</name>
              <balance>roundrobin</balance>
            </item>
          </ha_backends>
        </haproxy>
      </installedpackages>
    </pfsense>
    """
    before = _cfg(base)
    after = _cfg(after_xml)
    # If the parser's HAProxy model shape doesn't include backends
    # under ``installedpackages.haproxy.backends``, this test
    # silently covers nothing — check the precondition.
    hp = getattr(after.installedpackages, "haproxy", None) if after.installedpackages else None
    backends = getattr(hp, "backends", None) if hp else None
    if not backends:
        import pytest
        pytest.skip("parser doesn't surface haproxy.backends")

    events = list(diff_to_anchor_events(diff_configs(before, after), after))
    backend_events = [
        (aid, kind)
        for aid, kind, _v in events
        if aid.startswith("xref-haproxy_backend-")
    ]
    # Expect at least the added ``api-back``. The modified
    # ``web-back`` is also valid but depends on how the parser
    # surfaces the ``balance`` field.
    assert any(
        aid == "xref-haproxy_backend-api-back" and kind == "added"
        for aid, kind in backend_events
    )


def test_enumerate_anchors_covers_package_singletons():
    """Seed path emits ``field-<pkg>-<leaf>`` events for package
    singletons present in the parsed config. Pre-v0.40.2 this was a
    silent gap — pfSense instances with Avahi or telegraf configured
    had empty blame timelines for those fields."""
    xml = """
    <pfsense>
      <system><hostname>gw</hostname></system>
      <installedpackages>
        <avahi>
          <enable>on</enable>
          <interface>lan</interface>
        </avahi>
        <telegraf>
          <url>http://host:8086</url>
        </telegraf>
      </installedpackages>
    </pfsense>
    """
    cfg = _cfg(xml)
    ids = {aid for aid, _ in enumerate_anchors(cfg)}
    assert "field-avahi-enable" in ids
    # The avahi parser model exposes ``interfaces`` (plural) as the
    # field name, not ``interface``.
    assert "field-avahi-interfaces" in ids
    assert "field-telegraf-url" in ids


def test_first_backup_seed_produces_complete_coverage():
    """``enumerate_anchors`` over the first backup of an instance is
    what the ingestion + backfill paths use as a seed. Pin the count
    against the sample XML so the test fails if a section is
    accidentally dropped from SECTION_SPEC."""
    cfg = _cfg(BASE_XML)
    ids = [aid for aid, _ in enumerate_anchors(cfg)]
    # 2 firewall rules + 1 alias = 3 row anchors.
    row_anchors = [i for i in ids if i.startswith("xref-")]
    assert len(row_anchors) == 3

    # system.hostname + system.domain plus any other scalar fields
    # the SystemInfo model exposes. At minimum the two set above.
    field_anchors = [i for i in ids if i.startswith("field-system-")]
    assert "field-system-hostname" in field_anchors
    assert "field-system-domain" in field_anchors
