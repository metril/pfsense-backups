"""Build a ``{anchorId → (start_line, end_line)}`` map for a pfSense
config.xml.

Used by the web viewer to round-trip between the Structured tab and
the Raw XML tab at a stable focus point: the frontend renders rows
with ``id="xref-rule-{key}"`` / ``id="field-system-hostname"`` etc.,
and this module emits positions keyed the same way so a tab switch
can reveal the exact line in Monaco (or map a Monaco cursor line
back to a structured row).

Implementation uses ``lxml`` because stdlib ``xml.etree.ElementTree``
doesn't track source-line numbers. We keep the main ``pfsense_parser``
on ElementTree — lxml is a targeted dependency for this builder only.

The anchor-id conventions must match
[frontend/src/lib/xref.ts](../frontend/src/lib/xref.ts)'s
``itemId(kind, key)`` and ``rowAnchorId(scope, key)`` helpers plus the
``field-{section}-{fieldname}`` form used by singleton panels. Any
drift between the two sides produces a miss in the tab-switch sync;
positions would still cover every correctly-anchored element, just
not the one the operator is looking at.

v0.25.0 — accept an optional ``parsed: ParsedConfig``. When supplied,
firewall + NAT rule anchors are keyed off the parser's synthesized
``r.key`` (``tracker:…`` / ``hash:…`` / ``port_forward-N``) instead
of the raw ``<tracker>`` element; this pairs lxml's document-order
walk with the parser's identical walk so keys line up with the
frontend's ``rowAnchorId("rule" | "nat", r.key)`` emission. Without
``parsed`` we fall back to the best-effort tracker-only behavior so
tests that exercise the builder in isolation still pass.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from lxml import etree

if TYPE_CHECKING:
    from pfsense_shared.pfsense_parser import ParsedConfig

log = logging.getLogger(__name__)

# Anchor-id safe-charset — mirrors the ``safe`` helper in
# ``frontend/src/lib/xref.ts``. Any char outside ``[A-Za-z0-9_-]``
# becomes ``_``; the result plugs into a CSS selector / fragment.
_SAFE_RE = re.compile(r"[^A-Za-z0-9_-]")


def _safe(key: str) -> str:
    return _SAFE_RE.sub("_", key)


def _end_line(el: etree._Element) -> int:
    """Approximate end line of an element by walking its descendants
    and taking the max ``sourceline``. lxml does NOT track closing-
    tag positions directly, so the "end" is the last child's source
    line + 1 as a defensive fudge. Consumers use the range to map
    Monaco cursor → anchor (inclusive), so a slight overshoot is
    acceptable; undershoot would miss rows."""
    start = el.sourceline or 1
    last = start
    for desc in el.iter():
        sl = desc.sourceline
        if sl is not None and sl > last:
            last = sl
    return max(start, last) + 1


def _add(
    positions: dict[str, tuple[int, int]],
    anchor_id: str,
    el: etree._Element,
) -> None:
    start = el.sourceline or 1
    positions[anchor_id] = (start, _end_line(el))


def _findtext(el: etree._Element, tag: str) -> str | None:
    v = el.findtext(tag)
    if v is None:
        return None
    s = v.strip()
    return s or None


# ---------------------------------------------------------------- #
# Kind anchors — match ``itemId(kind, key)`` in frontend/src/lib/xref.ts.
# Each entry yields one ``xref-{kind}-{key}`` anchor per matched element.
# ---------------------------------------------------------------- #

_KIND_ANCHORS: list[tuple[str, str, str]] = [
    # (kind,                  xpath,                         key_tag)
    ("alias", "aliases/alias", "name"),
    ("gateway", "gateways/gateway_item", "name"),
    ("gateway_group", "gateways/gateway_group", "name"),
    ("schedule", "schedules/schedule", "name"),
    ("ca", "ca", "refid"),
    ("cert", "cert", "refid"),
    ("crl", "crl", "refid"),
    ("authserver", "system/authserver", "name"),
    ("openvpn_server", "openvpn/openvpn-server", "vpnid"),
    ("openvpn_client", "openvpn/openvpn-client", "vpnid"),
    ("openvpn_csc", "openvpn/openvpn-csc", "common_name"),
    ("ipsec_phase1", "ipsec/phase1", "ikeid"),
    ("ipsec_phase2", "ipsec/phase2", "uniqid"),
    ("lb_pool", "load_balancer/lbpool", "name"),
    ("user", "system/user", "name"),
    ("group", "system/group", "name"),
    ("vlan", "vlans/vlan", "vlanif"),
    # v0.18.0 — InterfaceGroup (``<ifgroups><ifgroupentry><ifname>``).
    # Missing here in v0.22.0–v0.24.0 meant clicking an interface_group
    # chip had no Raw-XML jump target and the blame drawer always
    # returned None for ``xref-interface_group-*``.
    ("interface_group", "ifgroups/ifgroupentry", "ifname"),
    # HAProxy backend pool — lives under installedpackages.
    ("haproxy_backend", "installedpackages/haproxy/ha_pools/item", "name"),
]


def _interface_anchors(
    root: etree._Element, positions: dict[str, tuple[int, int]]
) -> None:
    """Interfaces are keyed by the ELEMENT TAG NAME (``wan``, ``lan``,
    ``opt1``), not an inner field. pfSense stores each interface as
    a direct child of ``<interfaces>``."""
    interfaces = root.find("interfaces")
    if interfaces is None:
        return
    for iface in interfaces:
        tag = iface.tag
        if isinstance(tag, str):
            _add(positions, f"xref-interface-{_safe(tag)}", iface)


def _firewall_and_nat_anchors(
    root: etree._Element,
    positions: dict[str, tuple[int, int]],
    parsed: ParsedConfig | None,
) -> None:
    """Emit ``xref-rule-{key}`` and ``xref-nat-{key}`` positions.

    Two-mode: when ``parsed`` is available we iterate the lxml rules
    in document order and pair them one-for-one with the parser's
    ``firewall_rules`` / ``nat_rules`` lists — the parser walks the
    same ``<filter>/<rule>`` / ``<nat>/<rule>`` children in document
    order, so element N on one side matches entry N on the other.
    The parser's ``r.key`` is ``tracker:{tracker}`` when present,
    otherwise ``hash:{sha12}`` (firewall) / ``port_forward-N`` /
    ``hash:…`` (NAT). Those keys match what the frontend applies as
    DOM ids.

    When ``parsed`` is None we fall back to the raw ``<tracker>``
    value — tests exercise this path with ad-hoc XML fragments that
    don't need a full parse.
    """
    f_el = root.find("filter")
    if f_el is not None:
        rule_els = f_el.findall("rule")
        if parsed is not None and len(parsed.firewall_rules) == len(rule_els):
            for el, rule in zip(rule_els, parsed.firewall_rules, strict=True):
                _add(positions, f"xref-rule-{_safe(rule.key)}", el)
        else:
            for el in rule_els:
                key = _findtext(el, "tracker")
                if not key:
                    continue
                _add(positions, f"xref-rule-{_safe(key)}", el)

    n_el = root.find("nat")
    if n_el is not None and parsed is None:
        # Fallback mode (tests, any future caller that forgets to
        # pass ``parsed``): we can't compute the parser's synthesized
        # NAT keys without the parser. Warn loud enough that a new
        # call site can't silently ship degraded output — this is a
        # user-visible gap (NAT tab-switch misses every row).
        log.warning(
            "build_positions: parsed=None on a config that contains "
            "<nat> rules; xref-nat-* anchors will be skipped. Pass "
            "parsed=parse(xml_bytes) to emit parser-keyed anchors."
        )
    if n_el is not None and parsed is not None:
        # Mirror the exact walk order used by
        # ``pfsense_sections.nat.parse``:
        #   1. <nat><rule>          — port-forward
        #   2. <nat><onetoone>      — 1:1
        #   3. <nat><outbound><rule> — outbound NAT
        # so ``parsed.nat_rules[i]`` pairs with ``nat_els[i]``.
        nat_els: list[etree._Element] = []
        nat_els.extend(n_el.findall("rule"))
        nat_els.extend(n_el.findall("onetoone"))
        outbound = n_el.find("outbound")
        if outbound is not None:
            nat_els.extend(outbound.findall("rule"))
        if len(parsed.nat_rules) == len(nat_els):
            for el, nat_rule in zip(nat_els, parsed.nat_rules, strict=True):
                _add(positions, f"xref-nat-{_safe(nat_rule.key)}", el)
        else:
            # Length disagrees with parser — a comment / PI between
            # rule elements, an unknown NAT kind, etc. Fall back to
            # tracker-keyed anchors for the port-forward children.
            # Better to surface SOME tab-switch target than none; the
            # frontend's itemId miss gracefully degrades to the
            # section anchor on misses.
            for el in n_el.findall("rule"):
                key = _findtext(el, "tracker")
                if key:
                    _add(positions, f"xref-nat-{_safe(key)}", el)


# ---------------------------------------------------------------- #
# Section-level + field-level anchors for singleton config blocks.
# The Structured viewer renders these as ``<Dl>`` rows; each row's
# ``<dt>`` gets ``id="field-{section}-{childtag}"`` in the frontend
# so intersection tracking reports a stable field id.
# ---------------------------------------------------------------- #

# Sections that render as a single Dl of fields. Keyed by our
# internal section name (matches the ``fieldId`` prefix used by the
# frontend). ``xpath`` is the section root; ``inner_paths`` is an
# optional list of child XPaths whose *own* children should ALSO be
# emitted as field anchors on the same section key — used for
# wrapper elements like ``<vpn_openvpn_export><defaults>`` where the
# operator's fields live a level deeper than the section root.
_SINGLETON_SECTIONS: list[tuple[str, str, list[str]]] = [
    ("system", "system", []),
    ("dns", "dnsmasq", []),
    ("unbound", "unbound", []),
    ("ntpd", "ntpd", []),
    ("snmpd", "snmpd", []),
    ("syslog", "syslog", []),
    ("notifications", "notifications", []),
    ("ups", "ups", []),
    ("ftpproxy", "ftpproxy", []),
    ("hasync", "hasync", []),
    ("theme", "theme", []),
    ("diag", "diag", []),
    # v0.17+ packages — each package config lives under
    # ``installedpackages/{pkg}``; singleton panels bind to the pkg
    # root. Row panels (wireguard tunnels, snort interfaces, etc.)
    # don't go through this list.
    ("avahi", "installedpackages/avahi", []),
    ("miniupnpd", "installedpackages/miniupnpd", []),
    (
        "openvpn_client_export",
        "installedpackages/vpn_openvpn_export",
        ["defaults"],  # <defaults> wraps the actual toggle fields
    ),
    ("telegraf", "installedpackages/telegraf", []),
]


def _singleton_field_anchors(
    root: etree._Element, positions: dict[str, tuple[int, int]]
) -> None:
    for section, xpath, inner_paths in _SINGLETON_SECTIONS:
        el = root.find(xpath)
        if el is None:
            continue
        # Section-level anchor so the frontend can fall back to it
        # when a specific field doesn't carry a focus (e.g. the
        # operator just scrolled to the section title).
        _add(positions, f"section-{section}", el)
        # Every direct child of the section root.
        for child in el:
            tag = child.tag
            if not isinstance(tag, str):
                continue  # lxml emits Comment / PI objects as callables
            _add(positions, f"field-{section}-{_safe(tag)}", child)
        # Plus the direct children of any wrapper sub-elements (e.g.
        # ``<defaults>``). Wrapper-granular fields get the same
        # ``field-{section}-{tag}`` namespace so the frontend doesn't
        # need to know the wrapper path exists.
        for inner_path in inner_paths:
            inner = el.find(inner_path)
            if inner is None:
                continue
            for child in inner:
                tag = child.tag
                if not isinstance(tag, str):
                    continue
                _add(positions, f"field-{section}-{_safe(tag)}", child)


# ---------------------------------------------------------------- #
# Public API
# ---------------------------------------------------------------- #


def build_positions(
    xml_bytes: bytes,
    parsed: ParsedConfig | None = None,
) -> dict[str, tuple[int, int]]:
    """Parse ``xml_bytes`` with lxml and emit an anchorId→line-range
    map. Line numbers are 1-based to match Monaco.

    ``parsed`` is optional but recommended: when supplied, firewall
    + NAT rule anchors pair lxml's document-order walk with the
    parser's ``firewall_rules`` / ``nat_rules`` lists so keys match
    exactly what the frontend emits.

    Invalid XML raises ``lxml.etree.XMLSyntaxError`` (callers already
    handle that from the parallel main parse)."""
    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
    root = etree.fromstring(xml_bytes, parser=parser)

    positions: dict[str, tuple[int, int]] = {}

    _firewall_and_nat_anchors(root, positions, parsed)

    # Every (kind, xpath, key_tag) target — these match the xref
    # index's RefKinds one-for-one.
    for kind, xpath, key_tag in _KIND_ANCHORS:
        for el in root.findall(xpath):
            key = _findtext(el, key_tag)
            if not key:
                continue
            _add(positions, f"xref-{kind}-{_safe(key)}", el)

    _interface_anchors(root, positions)
    _singleton_field_anchors(root, positions)

    return positions
