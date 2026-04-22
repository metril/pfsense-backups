"""Projection helpers for the ``anchor_event`` log.

Two directions served here:

- ``diff_to_anchor_events(diff, parsed_after)`` — walks a
  ``ConfigDiff`` and yields ``(anchor_id, kind, value)`` tuples
  suitable for bulk-insert into ``AnchorEvent``. Used by both the
  ingestion path (one diff per new backup) and the backfill CLI
  (pairwise over every backup in the instance's history).

- ``enumerate_anchors(parsed)`` — walks a ``ParsedConfig`` and
  yields ``(anchor_id, value)`` for every anchor present. Used to
  seed events for the very first backup of an instance (no prior
  snapshot to diff against) and by the backfill CLI for the first
  item in each instance's chain.

Anchor taxonomy mirrors
``pfsense_shared/pfsense_anchor_values.py`` — same ``xref-`` /
``field-`` conventions that the frontend emits via ``xref.ts``. A
deliberate choice: the anchor_id a projector writes here is the
same string that ``resolve_anchor_value`` walks to, so the two
paths stay round-trippable.

The projector skips diff sections that don't map to a known anchor
kind (``gifs``, ``dyndns_entries``, ``static_routes``, etc.). Those
still surface in the ``ConfigDiff`` viewer — blame / tooltip /
cumulative just won't see them. Extending coverage is a matter of
adding a row to ``SECTION_SPEC`` below + teaching
``resolve_anchor_value`` the same scope.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from .pfsense_diff import ConfigDiff, SectionDiff
from .pfsense_parser import ParsedConfig


def _safe(key: str) -> str:
    """Sanitiser matching ``pfsense_anchor_values._safe`` and the
    frontend's ``safe()`` — any char outside ``[A-Za-z0-9_-]``
    becomes ``_``. Must stay in lockstep so events a projector
    emits here resolve against the frontend-generated IDs.
    """
    return re.sub(r"[^A-Za-z0-9_-]", "_", key)


# Row-shaped sections: ``(anchor_kind, anchor_key_field, diff_key_field)``.
#
# - ``anchor_kind``       — the ``{kind}`` in ``xref-{kind}-{key}``.
# - ``anchor_key_field``  — which attribute on the parsed row holds
#   the value the frontend uses in the anchor id. Matches
#   ``pfsense_anchor_values._ROW_SCOPES``.
# - ``diff_key_field``    — which attribute ``pfsense_diff._diff_list``
#   uses to identify the row. Usually the same, but ``vlans`` use
#   ``key`` for the diff and ``vlanif`` for the anchor, so the
#   projector has to translate via the parsed row.
SECTION_SPEC: dict[str, tuple[str, str, str]] = {
    "firewall_rules": ("rule", "key", "key"),
    "nat_rules": ("nat", "key", "key"),
    "aliases": ("alias", "name", "name"),
    "interfaces": ("interface", "key", "key"),
    "vlans": ("vlan", "vlanif", "key"),
    "gateways": ("gateway", "name", "name"),
    "gateway_groups": ("gateway_group", "name", "name"),
    "schedules": ("schedule", "name", "name"),
    "certificate_authorities": ("ca", "refid", "refid"),
    "certificates": ("cert", "refid", "refid"),
    "crls": ("crl", "refid", "refid"),
    "authservers": ("authserver", "name", "name"),
    "openvpn_servers": ("openvpn_server", "vpnid", "vpnid"),
    "openvpn_clients": ("openvpn_client", "vpnid", "vpnid"),
    "openvpn_cscs": ("openvpn_csc", "common_name", "common_name"),
    "ipsec_phase1": ("ipsec_phase1", "ikeid", "ikeid"),
    "ipsec_phase2": ("ipsec_phase2", "uniqid", "uniqid"),
    "lb_pools": ("lb_pool", "name", "name"),
    "users": ("user", "name", "name"),
    "groups": ("group", "name", "name"),
    "interface_groups": ("interface_group", "ifname", "ifname"),
}


# Reverse lookup: ``{anchor_kind: section_name}``. Used by the
# cumulative-changes endpoint to carry a ``section`` field back to
# the UI for filtering/grouping.
ANCHOR_KIND_TO_SECTION: dict[str, str] = {
    spec[0]: section for section, spec in SECTION_SPEC.items()
}


# Singleton sections: ``{config_diff_section: anchor_scope}``. The
# anchor scope is usually identical to the section name; we keep
# both columns for symmetry with the row-shaped table above.
SINGLETON_SPEC: dict[str, str] = {
    "system": "system",
    "dns": "dns",
    "hasync": "hasync",
    "ntpd": "ntpd",
    "snmpd": "snmpd",
    "syslog": "syslog",
    "notifications": "notifications",
    "ups": "ups",
    "ftpproxy": "ftpproxy",
    "diag": "diag",
    "theme": "theme",
}


# Reverse alias: ``{config_diff_section: {pydantic_field: (scope, xml_tag)}}``.
#
# Mirrors ``pfsense_anchor_values._FIELD_ALIASES`` in reverse: when
# the diff surfaces a FieldChange under a Pydantic field name that
# doesn't match its XML tag, rescope the emitted anchor id so it
# matches what the positions map and the frontend ``fieldId`` calls
# produce. Example: ``DnsConfig`` flattens ``<dnsmasq>`` and
# ``<unbound>`` into one record — a change to
# ``dnsmasq_enabled`` must surface as ``field-dns-enable``, a change
# to ``unbound_enabled`` as ``field-unbound-enable``.
#
# New entries must stay in lockstep with the resolver's forward table
# or ids the projector emits won't be resolvable.
_SINGLETON_FIELD_RESCOPE: dict[str, dict[str, tuple[str, str]]] = {
    "dns": {
        "dnsmasq_enabled": ("dns", "enable"),
        "dnsmasq_port": ("dns", "port"),
        "unbound_enabled": ("unbound", "enable"),
        "unbound_port": ("unbound", "port"),
    },
}


# Package singletons live under ``ParsedConfig.installedpackages``
# and don't have their own ``ConfigDiff`` field. Instead, changes
# surface as ``FieldChange`` entries inside
# ``diff.installedpackages.modified[0].changes[]`` with dot-notation
# paths like ``avahi.enable``, ``telegraf.url``. The projector
# unpacks those at the top of ``diff_to_anchor_events``.
#
# Mirrors the package entries of
# ``pfsense_anchor_values._SINGLETON_PATH``. Any new package the
# resolver learns about must also land here, or blame for its
# fields will be empty on the indexed path.
PACKAGE_SINGLETON_SPEC: dict[str, str] = {
    "avahi": "avahi",
    "miniupnpd": "miniupnpd",
    "openvpn_client_export": "openvpn_client_export",
    "telegraf": "telegraf",
}


# Package-level ROW lists: same anchor taxonomy as ``SECTION_SPEC``
# but nested under ``installedpackages``. Entries map
# ``<package>.<attr>`` (the dotted path on ``parsed.installedpackages``)
# to ``(anchor_kind, anchor_key_field)``. Mirrors the dotted entries
# in ``pfsense_anchor_values._ROW_SCOPES`` (only ``haproxy_backend``
# today; extend as more are added to the resolver).
PACKAGE_ROW_SPEC: dict[str, tuple[str, str]] = {
    "haproxy.backends": ("haproxy_backend", "name"),
}


# Scope aliasing for Pydantic-flattened XML sections — see
# ``_SINGLETON_FIELD_RESCOPE`` below. The major gaps flagged during
# the v0.40.0 review (DNS/unbound drift, reorder+modified signal,
# NAT hash-key instability) are all fixed in v0.40.1; any new gap
# documentation belongs next to the code it affects.


# Reverse lookup: ``{anchor_scope: config_diff_section}``. Used by
# the cumulative-changes endpoint + anchor_id → section decoder
# below.
SINGLETON_SCOPE_TO_SECTION: dict[str, str] = {
    scope: section for section, scope in SINGLETON_SPEC.items()
}


_ANCHOR_RE = re.compile(r"^(xref|field|section)-([A-Za-z0-9_]+?)(?:-(.+))?$")


def section_for_anchor(anchor_id: str) -> str | None:
    """Decode an ``anchor_id`` back to its ``ConfigDiff`` section
    name — the string the cumulative-changes UI uses for grouping.

    Returns ``None`` for anchors we don't have a section for
    (malformed ID, or a kind outside our maps).
    """
    m = _ANCHOR_RE.match(anchor_id)
    if m is None:
        return None
    namespace, scope, _tail = m.group(1), m.group(2), m.group(3)
    if namespace == "xref":
        return ANCHOR_KIND_TO_SECTION.get(scope)
    if namespace == "field":
        return SINGLETON_SCOPE_TO_SECTION.get(scope)
    if namespace == "section":
        return SINGLETON_SCOPE_TO_SECTION.get(scope) or scope
    return None


def _anchor_key_from_row(
    row: dict[str, Any], anchor_key_field: str
) -> str | None:
    raw = row.get(anchor_key_field)
    if raw is None:
        return None
    return _safe(str(raw))


def _row_anchor_id(kind: str, row: dict[str, Any], anchor_key_field: str) -> str | None:
    key = _anchor_key_from_row(row, anchor_key_field)
    if key is None:
        return None
    return f"xref-{kind}-{key}"


def _rows_from_parsed(
    parsed: ParsedConfig, section_name: str
) -> list[Any]:
    rows = getattr(parsed, section_name, None)
    return list(rows) if rows else []


def _descend(obj: Any, path: str) -> Any:
    """Walk a dotted attribute path; return None if any segment is
    missing. Mirrors ``pfsense_anchor_values._descend`` — kept local
    here to avoid a cross-module dependency for one tiny helper.
    """
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        cur = getattr(cur, part, None)
    return cur


def _dump_row(row: Any) -> dict[str, Any]:
    if hasattr(row, "model_dump"):
        dumped = row.model_dump()
        return dict(dumped) if isinstance(dumped, dict) else {}
    if isinstance(row, dict):
        return dict(row)
    return {}


def diff_to_anchor_events(
    diff: ConfigDiff,
    parsed_after: ParsedConfig,
) -> Iterator[tuple[str, str, Any]]:
    """Project a ``ConfigDiff`` + the post-change ``ParsedConfig``
    into ``(anchor_id, kind, value)`` tuples.

    ``parsed_after`` is required to resolve the post-change row for
    ``modified`` / ``reordered`` events — ``ItemDiff`` only carries
    per-field changes, not the full row. For ``added`` / ``removed``,
    ``SectionDiff`` already carries the full dict so ``parsed_after``
    is unused on that path.

    Emits ``kind`` values: ``added`` / ``modified`` / ``removed`` /
    ``reordered``. ``value`` is a plain dict for row-shaped anchors
    and a scalar for field-shaped anchors.
    """
    for section_name, (anchor_kind, anchor_key_field, diff_key_field) in (
        SECTION_SPEC.items()
    ):
        section: SectionDiff | None = getattr(diff, section_name, None)
        if section is None:
            continue

        for row in section.added:
            aid = _row_anchor_id(anchor_kind, row, anchor_key_field)
            if aid is not None:
                yield aid, "added", row

        for row in section.removed:
            aid = _row_anchor_id(anchor_kind, row, anchor_key_field)
            if aid is not None:
                yield aid, "removed", row

        if section.modified or section.reordered:
            # Build a lookup from the diff's key-field value (the
            # ``ItemDiff.key`` we'll see in .modified / .reordered)
            # back to the parsed row. Done once per section.
            by_diff_key: dict[str, dict[str, Any]] = {}
            for row in _rows_from_parsed(parsed_after, section_name):
                row_dict = _dump_row(row)
                k = row_dict.get(diff_key_field)
                if k is None:
                    continue
                by_diff_key[str(k)] = row_dict

            for item in section.modified:
                row_dict = by_diff_key.get(item.key)
                if row_dict is None:
                    continue
                aid = _row_anchor_id(anchor_kind, row_dict, anchor_key_field)
                if aid is not None:
                    yield aid, "modified", row_dict

            # Reorder events are emitted INDEPENDENTLY of modified —
            # a firewall rule that was both edited AND moved produces
            # two events at the same ``occurred_at`` (one ``modified``,
            # one ``reordered``). pfSense evaluates firewall rules
            # top-to-bottom, so the position change is operationally
            # distinct from any field edit. The cumulative-changes
            # page and blame drawer show both, giving an audit-
            # friendly trail.
            for r in section.reordered:
                row_dict = by_diff_key.get(r.key)
                if row_dict is None:
                    continue
                aid = _row_anchor_id(anchor_kind, row_dict, anchor_key_field)
                if aid is not None:
                    yield aid, "reordered", row_dict

    for section_name, scope in SINGLETON_SPEC.items():
        section = getattr(diff, section_name, None)
        if section is None:
            continue

        rescope_map = _SINGLETON_FIELD_RESCOPE.get(section_name, {})

        def _rescope(
            field_name: str,
            *,
            default_scope: str = scope,
            rescope_map: dict[str, tuple[str, str]] = rescope_map,
        ) -> tuple[str, str] | None:
            # Return ``(effective_scope, xml_tag)`` for a Pydantic
            # field name, or ``None`` if the field isn't addressable
            # as an anchor (dotted paths, etc.).
            if "." in field_name:
                return None
            if field_name in rescope_map:
                return rescope_map[field_name]
            return (default_scope, field_name)

        # Singleton ``added`` == whole section sprouted. Emit one
        # event per field inside the new dict.
        for whole in section.added:
            for field, value in whole.items():
                resc = _rescope(field)
                if resc is None:
                    continue
                eff_scope, eff_tag = resc
                yield f"field-{eff_scope}-{eff_tag}", "added", value

        for whole in section.removed:
            for field, value in whole.items():
                resc = _rescope(field)
                if resc is None:
                    continue
                eff_scope, eff_tag = resc
                yield f"field-{eff_scope}-{eff_tag}", "removed", value

        for item in section.modified:
            for change in item.changes:
                resc = _rescope(change.field)
                if resc is None:
                    # Deeper-nested field paths are not addressable
                    # by the current resolver. Revisit when the
                    # resolver learns dotted singleton fields.
                    continue
                eff_scope, eff_tag = resc
                if change.after is None and change.before is not None:
                    kind = "removed"
                    value: Any = change.before
                elif change.before is None and change.after is not None:
                    kind = "added"
                    value = change.after
                else:
                    kind = "modified"
                    value = change.after
                yield f"field-{eff_scope}-{eff_tag}", kind, value

    # Package singletons live inside ``diff.installedpackages`` — an
    # optional-model diff with ``modified[0].changes[]`` carrying
    # dot-notation paths. Top-level prefix identifies the package.
    installedpackages = getattr(diff, "installedpackages", None)
    if installedpackages is not None:
        # Whole installedpackages block appeared / disappeared.
        for whole in installedpackages.added:
            for pkg, pkg_scope in PACKAGE_SINGLETON_SPEC.items():
                pkg_value = whole.get(pkg)
                if not isinstance(pkg_value, dict):
                    continue
                for leaf, leaf_value in pkg_value.items():
                    if "." in leaf or not isinstance(leaf, str):
                        continue
                    yield f"field-{pkg_scope}-{leaf}", "added", leaf_value
        for whole in installedpackages.removed:
            for pkg, pkg_scope in PACKAGE_SINGLETON_SPEC.items():
                pkg_value = whole.get(pkg)
                if not isinstance(pkg_value, dict):
                    continue
                for leaf, leaf_value in pkg_value.items():
                    if "." in leaf or not isinstance(leaf, str):
                        continue
                    yield f"field-{pkg_scope}-{leaf}", "removed", leaf_value
        # Field-level installedpackages changes — the common path.
        # ``change.field`` shapes we handle:
        #   ``<pkg>.<leaf>``                              → singleton field
        #   ``<pkg>.<list_attr>.<index_or_key>.<subfield>``→ package row
        #
        # Row-level changes come through as one FieldChange per
        # changed sub-field. We group them by ``(list_attr_path, key)``
        # so we emit ONE event per changed row (with the full row
        # dict from ``parsed_after``) rather than a storm of events
        # per sub-field.
        package_row_hits: dict[tuple[str, str], str] = {}
        for item in installedpackages.modified:
            for change in item.changes:
                parts = change.field.split(".")
                if len(parts) == 2:
                    pkg, leaf = parts
                    pkg_scope = PACKAGE_SINGLETON_SPEC.get(pkg)
                    if pkg_scope is None:
                        continue
                    if change.after is None and change.before is not None:
                        yield f"field-{pkg_scope}-{leaf}", "removed", change.before
                    elif change.before is None and change.after is not None:
                        yield f"field-{pkg_scope}-{leaf}", "added", change.after
                    else:
                        yield f"field-{pkg_scope}-{leaf}", "modified", change.after
                elif len(parts) >= 4:
                    # Check for known package row scopes by matching
                    # the longest matching prefix against PACKAGE_ROW_SPEC.
                    list_path = None
                    for candidate in PACKAGE_ROW_SPEC:
                        candidate_parts = candidate.split(".")
                        if parts[: len(candidate_parts)] == candidate_parts:
                            list_path = candidate
                            break
                    if list_path is None:
                        continue
                    row_key_part_idx = len(list_path.split("."))
                    if row_key_part_idx >= len(parts):
                        continue
                    row_key = parts[row_key_part_idx]
                    # Classify event kind by the first change we see
                    # for this row — later sub-field changes just
                    # reinforce the same event. Pure "row added"
                    # produces changes with ``before=None``; "row
                    # removed" with ``after=None``; otherwise
                    # ``modified``.
                    key_tuple = (list_path, row_key)
                    if key_tuple in package_row_hits:
                        continue
                    if change.after is None and change.before is not None:
                        package_row_hits[key_tuple] = "removed"
                    elif change.before is None and change.after is not None:
                        package_row_hits[key_tuple] = "added"
                    else:
                        package_row_hits[key_tuple] = "modified"

        # Emit package-row events. For adds / modifies we pull the
        # current row dict from ``parsed_after``; for removes the row
        # no longer exists in ``parsed_after``, so we emit ``None`` as
        # value (matches the singleton-removed shape — caller JSON-
        # encodes to null).
        for (list_path, row_key), kind in package_row_hits.items():
            spec = PACKAGE_ROW_SPEC.get(list_path)
            if spec is None:
                continue
            anchor_kind, anchor_key_field = spec
            installed_pkg = getattr(parsed_after, "installedpackages", None)
            row_list = (
                _descend(installed_pkg, list_path)
                if installed_pkg is not None
                else None
            )
            row_dict: dict[str, Any] | None = None
            if row_list:
                for row in row_list:
                    d = _dump_row(row)
                    if str(d.get(anchor_key_field)) == row_key or str(
                        d.get("key")
                    ) == row_key:
                        row_dict = d
                        break
            # Derive the sanitised anchor key from the resolved row
            # when available; fall back to the diff's key segment.
            anchor_key_value: str | None = None
            if row_dict is not None:
                raw = row_dict.get(anchor_key_field)
                if raw is not None:
                    anchor_key_value = _safe(str(raw))
            if anchor_key_value is None:
                anchor_key_value = _safe(row_key)
            aid = f"xref-{anchor_kind}-{anchor_key_value}"
            yield aid, kind, row_dict


def enumerate_anchors(
    parsed: ParsedConfig,
) -> Iterator[tuple[str, Any]]:
    """Walk a ``ParsedConfig`` and yield ``(anchor_id, value)`` for
    every anchor we know how to address.

    Used to seed events for the very first backup of an instance —
    without this, a field set at instance creation and never changed
    would have an empty blame history.
    """
    for section_name, (anchor_kind, anchor_key_field, _diff_key_field) in (
        SECTION_SPEC.items()
    ):
        for row in _rows_from_parsed(parsed, section_name):
            row_dict = _dump_row(row)
            aid = _row_anchor_id(anchor_kind, row_dict, anchor_key_field)
            if aid is not None:
                yield aid, row_dict

    for section_name, scope in SINGLETON_SPEC.items():
        section_obj = getattr(parsed, scope, None)
        if section_obj is None:
            continue
        if not hasattr(section_obj, "model_dump"):
            continue
        dumped = section_obj.model_dump()
        if not isinstance(dumped, dict):
            continue
        rescope_map = _SINGLETON_FIELD_RESCOPE.get(section_name, {})
        for field, value in dumped.items():
            if "." in field or not isinstance(field, str):
                continue
            if field in rescope_map:
                eff_scope, eff_tag = rescope_map[field]
            else:
                eff_scope, eff_tag = scope, field
            yield f"field-{eff_scope}-{eff_tag}", value

    # Package singletons — seed from ``parsed.installedpackages.<pkg>``
    # for each configured package. Same shape as the main singleton
    # loop above but one level deeper on the parsed tree.
    installedpackages = getattr(parsed, "installedpackages", None)
    if installedpackages is not None:
        for pkg, pkg_scope in PACKAGE_SINGLETON_SPEC.items():
            pkg_obj = getattr(installedpackages, pkg, None)
            if pkg_obj is None or not hasattr(pkg_obj, "model_dump"):
                continue
            dumped = pkg_obj.model_dump()
            if not isinstance(dumped, dict):
                continue
            for field, value in dumped.items():
                if "." in field or not isinstance(field, str):
                    continue
                yield f"field-{pkg_scope}-{field}", value

        # Package-level ROW lists (HAProxy backends, etc.). Walk each
        # configured dotted path and emit one event per row.
        for list_path, (anchor_kind, anchor_key_field) in PACKAGE_ROW_SPEC.items():
            row_list = _descend(installedpackages, list_path)
            if not row_list:
                continue
            for row in row_list:
                row_dict = _dump_row(row)
                aid = _row_anchor_id(anchor_kind, row_dict, anchor_key_field)
                if aid is not None:
                    yield aid, row_dict
