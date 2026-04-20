"""Resolve a viewer anchor-id to the value it represents inside a
``ParsedConfig``. Used by the anchor-history endpoint (v0.24.0)
that powers the per-field blame drawer — we walk every backup of an
instance and record the anchor's value as it evolves over time.

Anchor-id conventions mirror
[frontend/src/lib/xref.ts](../frontend/src/lib/xref.ts)'s
``itemId`` / ``rowAnchorId`` / ``fieldId`` helpers:

- ``xref-{kind}-{key}``      — row in the corresponding list. Kind is
  one of ``rule``, ``nat``, ``alias``, ``interface``, ``vlan``,
  ``gateway``, ``gateway_group``, ``schedule``, ``ca``, ``cert``,
  ``crl``, ``authserver``, ``openvpn_server``, ``openvpn_client``,
  ``ipsec_phase1``, ``lb_pool``, ``user``, ``group``.
- ``field-{section}-{name}`` — a single field inside a singleton
  panel (``<system>``, ``<dns>``, etc.).
- ``section-{section}``       — falls through to the whole section
  object; rarely useful but cheap to support.

The resolver returns a ``dict[str, Any] | str | None`` — a dict for
row-shaped targets, a scalar for field-level lookups, ``None`` when
the anchor doesn't resolve against the provided config. Callers
compare two successive values with ``==``; ``None`` ↔ non-None still
counts as a change so deletions / creations surface in the blame.
"""

from __future__ import annotations

import re
from typing import Any

from pfsense_shared.pfsense_parser import ParsedConfig

# ---------------------------------------------------------------- #
# anchor kind / scope → (ParsedConfig field, row-key field)
# ---------------------------------------------------------------- #

# Row-shaped anchors. Looks up the list on ParsedConfig, finds the
# row where ``getattr(row, key_field) == key``, and returns a dict of
# the row's fields (model_dump).
_ROW_SCOPES: dict[str, tuple[str, str]] = {
    "rule": ("firewall_rules", "tracker"),
    # NAT rules don't have a reliable ``<tracker>`` in the XML; the
    # viewer's ``rowAnchorId("nat", r.key)`` uses the parser's
    # synthesized ``key`` (``hash:…`` or ``port_forward-N``). Match
    # on that same ``key`` field.
    "nat": ("nat_rules", "key"),
    "alias": ("aliases", "name"),
    "interface": ("interfaces", "key"),
    "vlan": ("vlans", "vlanif"),
    "gateway": ("gateways", "name"),
    "gateway_group": ("gateway_groups", "name"),
    "schedule": ("schedules", "name"),
    "ca": ("certificate_authorities", "refid"),
    "cert": ("certificates", "refid"),
    "crl": ("crls", "refid"),
    "authserver": ("authservers", "name"),
    "openvpn_server": ("openvpn_servers", "vpnid"),
    "openvpn_client": ("openvpn_clients", "vpnid"),
    "ipsec_phase1": ("ipsec_phase1", "ikeid"),
    "lb_pool": ("lb_pools", "name"),
    "user": ("users", "name"),
    "group": ("groups", "name"),
}

# Singleton sections — ``field-{section}-{name}`` reads
# ``getattr(getattr(cfg, SINGLETON_PATH[section]), name)``. Most
# frontend "section names" match ParsedConfig field names one-for-one;
# the exceptions map via this table.
_SINGLETON_PATH: dict[str, str] = {
    "system": "system",
    "dns": "dns",
    # ``unbound`` folds into the same ``dns`` record on the
    # ParsedConfig; the singleton-field anchor just looks up an
    # unbound-specific field on it (``unbound_enabled``, ...).
    "unbound": "dns",
    "hasync": "hasync",
    "ntpd": "ntpd",
    "snmpd": "snmpd",
    "syslog": "syslog",
    "notifications": "notifications",
    "ups": "ups",
    "ftpproxy": "ftpproxy",
    "diag": "diag",
}

_ANCHOR_RE = re.compile(r"^(xref|field|section)-([A-Za-z0-9_]+?)(?:-(.+))?$")


def _safe(key: str) -> str:
    """Mirror of the ``safe`` sanitiser used on the frontend: any char
    outside ``[A-Za-z0-9_-]`` becomes ``_``. We sanitise BOTH the
    caller's anchor tail and the candidate row keys before comparing
    so keys with ``.`` / ``|`` / ``:`` (composite trackers, qualified
    aliases, etc.) still match."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", key)


def _row_to_dict(row: Any) -> dict[str, Any]:
    if hasattr(row, "model_dump"):
        result = row.model_dump()
        # Cast to dict[str, Any] for mypy — model_dump returns
        # ``dict[str, Any]`` already but the inferred return type is
        # ``Any`` without the cast.
        return dict(result)
    if isinstance(row, dict):
        return dict(row)
    return {"value": row}


def resolve_anchor_value(
    cfg: ParsedConfig, anchor_id: str
) -> dict[str, Any] | str | None:
    """Return the value the given anchor points at inside ``cfg``.

    Returns ``None`` when the anchor doesn't resolve. Rows missing
    from a config (e.g. a firewall rule deleted in a later backup)
    surface as ``None`` — the blame drawer uses that to label the
    change as a removal.
    """
    m = _ANCHOR_RE.match(anchor_id)
    if not m:
        return None
    namespace, scope, tail = m.group(1), m.group(2), m.group(3)

    if namespace == "section":
        # ``section-{name}`` — return the whole section object if we
        # know it's a singleton; rows sit under row scopes already.
        attr = _SINGLETON_PATH.get(scope)
        if attr is None:
            return None
        section = getattr(cfg, attr, None)
        return _row_to_dict(section) if section is not None else None

    if namespace == "field":
        if tail is None:
            return None
        attr = _SINGLETON_PATH.get(scope)
        if attr is None:
            return None
        section = getattr(cfg, attr, None)
        if section is None:
            return None
        # Direct attribute lookup on the Pydantic model. The field
        # names on the model mirror the XML tag names one-to-one for
        # everything the frontend emits a ``fieldId`` for.
        return _stringify(getattr(section, tail, None))

    # namespace == "xref"
    if tail is None:
        return None
    mapping = _ROW_SCOPES.get(scope)
    if mapping is None:
        return None
    list_attr, key_attr = mapping
    rows = getattr(cfg, list_attr, None)
    if rows is None:
        return None
    wanted = _safe(tail)
    for row in rows:
        candidate = getattr(row, key_attr, None)
        if candidate is None:
            continue
        if _safe(str(candidate)) == wanted:
            return _row_to_dict(row)
    return None


def _stringify(value: Any) -> str | None:
    """Scalar / list → short string. ``None`` → ``None``.

    Keeps the blame drawer's values compact: lists render as
    comma-separated, booleans as ``yes``/``no``, anything else as
    ``str()``. JSON-level shapes (``dict``) fall through to repr so
    the drawer renderer can still diff them — rare path."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return ", ".join(_stringify(v) or "" for v in value)
    return str(value)
