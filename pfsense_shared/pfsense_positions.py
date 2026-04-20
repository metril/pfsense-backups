"""Build a ``{anchorId → (start_line, end_line)}`` map for a pfSense
config.xml.

Used by the web viewer to round-trip between the Structured tab and
the Raw XML tab at a stable focus point: the frontend renders rows
with ``id="xref-rule-{tracker}"`` / ``id="field-system-hostname"``
etc., and this module emits positions keyed the same way so a tab
switch can reveal the exact line in Monaco (or map a Monaco cursor
line back to a structured row).

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
"""

from __future__ import annotations

import re

from lxml import etree

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


# ---------------------------------------------------------------- #
# Row anchors — match ``itemId(kind, key)`` /
# ``rowAnchorId(scope, key)`` in frontend/src/lib/xref.ts.
#
# Each entry is (xpath, kind, key_getter). ``key_getter`` receives
# the matched element and returns the key string (or None to skip).
# ---------------------------------------------------------------- #


def _findtext(el: etree._Element, tag: str) -> str | None:
    v = el.findtext(tag)
    if v is None:
        return None
    s = v.strip()
    return s or None


_ROW_RULES: list[tuple[str, str, str]] = [
    # Firewall rules — anchored via ``rowAnchorId("rule", tracker)``.
    # Note the scope is ``rule`` not ``xref-rule`` in the frontend
    # helper; the resulting id is ``xref-rule-{tracker}``.
    ("filter/rule", "rule", "tracker"),
    # NAT rules intentionally NOT emitted here: the frontend
    # ``rowAnchorId("nat", r.key)`` uses the parser's synthesized
    # ``key`` (``hash:…``), which lxml can't compute without also
    # running the main ElementTree parser. Adding tracker-keyed
    # entries would only produce orphans. A future release can
    # restore NAT positions by piggy-backing on the Python parser's
    # output alongside the lxml walk.
]

# Anchor kind → XML container path → key attribute. Each entry yields
# one ``xref-{kind}-{key}`` row anchor.
_KIND_ANCHORS: list[tuple[str, str, str]] = [
    # (kind,                        xpath,                      key_tag)
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
    ("ipsec_phase1", "ipsec/phase1", "ikeid"),
    ("lb_pool", "load_balancer/lbpool", "name"),
    ("user", "system/user", "name"),
    ("group", "system/group", "name"),
    ("vlan", "vlans/vlan", "vlanif"),
    # HAProxy backend — lives under installedpackages.
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
        _add(positions, f"xref-interface-{_safe(iface.tag)}", iface)


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


def build_positions(xml_bytes: bytes) -> dict[str, tuple[int, int]]:
    """Parse ``xml_bytes`` with lxml and emit an anchorId→line-range
    map. Line numbers are 1-based to match Monaco. Invalid XML raises
    ``lxml.etree.XMLSyntaxError`` (callers already handle that from
    the parallel main parse)."""
    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
    root = etree.fromstring(xml_bytes, parser=parser)

    positions: dict[str, tuple[int, int]] = {}

    # Rule-shaped rows (firewall + NAT variants share a scope).
    for xpath, scope, key_tag in _ROW_RULES:
        for el in root.findall(xpath):
            key = _findtext(el, key_tag)
            if not key:
                continue
            _add(positions, f"xref-{scope}-{_safe(key)}", el)

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
