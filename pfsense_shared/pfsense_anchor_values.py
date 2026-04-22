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
  ``openvpn_csc``, ``ipsec_phase1``, ``ipsec_phase2``, ``lb_pool``,
  ``user``, ``group``, ``interface_group``, ``haproxy_backend``.
- ``field-{section}-{name}`` — a single field inside a singleton
  panel (``<system>``, ``<dns>``, etc.). ``section`` may refer to a
  package singleton (``avahi``, ``miniupnpd``, ``telegraf``,
  ``openvpn_client_export``) — the resolver walks a dotted path on
  ``ParsedConfig`` for those.
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
    "rule": ("firewall_rules", "key"),
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
    "openvpn_csc": ("openvpn_cscs", "common_name"),
    "ipsec_phase1": ("ipsec_phase1", "ikeid"),
    "ipsec_phase2": ("ipsec_phase2", "uniqid"),
    "lb_pool": ("lb_pools", "name"),
    "user": ("users", "name"),
    "group": ("groups", "name"),
    "interface_group": ("interface_groups", "ifname"),
    # Package-level row list — dotted path descends into
    # ``installedpackages.haproxy.backends``. The resolver handles
    # dotted paths in ``list_attr``.
    "haproxy_backend": ("installedpackages.haproxy.backends", "name"),
}

# Field-level aliases: ``{(scope, xml_tag): pydantic_field_name}``.
#
# The anchor-id taxonomy is tag-based (drives the positions map + the
# frontend's ``fieldId`` calls), but some Pydantic sections flatten
# two XML subtrees into a single model — ``DnsConfig`` merges
# ``<dnsmasq>`` and ``<unbound>`` into one record with prefixed
# fields. When the resolver sees ``field-dns-enable`` it has to
# translate ``enable`` → ``dnsmasq_enabled`` on the scope's target
# model; ``field-unbound-enable`` → ``unbound_enabled``. Without this
# table both anchor ids resolve to None because ``DnsConfig`` has no
# literal ``enable`` field.
#
# New aliases land here AND in
# ``pfsense_shared/anchor_events._SINGLETON_FIELD_ALIASES`` so the
# projector emits the same ids the resolver can look up.
_FIELD_ALIASES: dict[tuple[str, str], str] = {
    ("dns", "enable"): "dnsmasq_enabled",
    ("dns", "port"): "dnsmasq_port",
    ("unbound", "enable"): "unbound_enabled",
    ("unbound", "port"): "unbound_port",
}


# Singleton sections — ``field-{section}-{name}`` reads
# ``getattr(getattr(cfg, SINGLETON_PATH[section]), name)``. The value
# may be a dotted attribute path (``installedpackages.avahi``) so
# package-level singletons resolve without special-casing.
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
    "theme": "theme",
    # Package-level singletons. Dotted paths descend
    # ParsedConfig.installedpackages.<pkg>.
    "avahi": "installedpackages.avahi",
    "miniupnpd": "installedpackages.miniupnpd",
    "openvpn_client_export": "installedpackages.openvpn_client_export",
    "telegraf": "installedpackages.telegraf",
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


def _descend(obj: Any, path: str) -> Any:
    """Walk a dotted attribute path; return ``None`` if any segment
    doesn't exist."""
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        cur = getattr(cur, part, None)
    return cur


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
        path = _SINGLETON_PATH.get(scope)
        if path is None:
            return None
        section = _descend(cfg, path)
        return _row_to_dict(section) if section is not None else None

    if namespace == "field":
        if tail is None:
            return None
        path = _SINGLETON_PATH.get(scope)
        if path is None:
            return None
        section = _descend(cfg, path)
        if section is None:
            return None
        # Direct attribute lookup on the Pydantic model. The field
        # names on the model mirror the XML tag names one-to-one for
        # most scopes; the ``_FIELD_ALIASES`` table handles the
        # scopes where the parser merges two XML subtrees into one
        # Pydantic record (e.g. ``DnsConfig`` holds both dnsmasq and
        # unbound fields under prefixed names).
        effective_tail = _FIELD_ALIASES.get((scope, tail), tail)
        return _stringify(getattr(section, effective_tail, None))

    # namespace == "xref"
    if tail is None:
        return None
    mapping = _ROW_SCOPES.get(scope)
    if mapping is None:
        return None
    list_attr, key_attr = mapping
    # ``list_attr`` may be dotted (``installedpackages.haproxy.backends``)
    # for row lists that live under a nested model.
    rows = _descend(cfg, list_attr) if "." in list_attr else getattr(cfg, list_attr, None)
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
