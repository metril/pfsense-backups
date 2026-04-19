"""Structured diff between two ``ParsedConfig`` snapshots.

Output is a per-section ``SectionDiff`` — added / removed / modified /
reordered lists plus an ``unchanged_count`` — that the frontend renders
as a summary strip with expandable per-section detail. For dict-shaped
sections (``system``, ``revision``, ``dns``) we emit one pseudo-item
with field-level changes so the rendering path is uniform.

Design notes:

- List sections are matched on their section-specific stable ``key``
  attribute (tracker for firewall, name for aliases, etc.). Added and
  removed items are surfaced as dicts (the full item) so the UI can
  show the new / old config inline without a second lookup.
- Modified items produce ``FieldChange`` entries — one per differing
  leaf, using dot-notation for nested structure (``source.network``,
  ``webgui.port``). This makes the diff cheap to render as a table.
- Order changes matter for firewall and NAT port-forward rules
  (pfSense evaluates top-to-bottom). Those sections emit a
  ``reordered`` list so "same rules, shuffled" doesn't silently
  pass review.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

from .pfsense_parser import ParsedConfig


class FieldChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    before: Any
    after: Any


class ItemDiff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    changes: list[FieldChange]


class ReorderEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    old_index: int
    new_index: int


class SectionDiff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    modified: list[ItemDiff] = []
    reordered: list[ReorderEvent] = []
    unchanged_count: int = 0

    @property
    def is_empty(self) -> bool:
        return (
            not self.added
            and not self.removed
            and not self.modified
            and not self.reordered
        )


class ConfigDiff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system: SectionDiff = SectionDiff()
    revision: SectionDiff = SectionDiff()
    sysctl: SectionDiff = SectionDiff()
    cron: SectionDiff = SectionDiff()
    interfaces: SectionDiff = SectionDiff()
    gateways: SectionDiff = SectionDiff()
    gateway_groups: SectionDiff = SectionDiff()
    static_routes: SectionDiff = SectionDiff()
    firewall_rules: SectionDiff = SectionDiff()
    nat_rules: SectionDiff = SectionDiff()
    aliases: SectionDiff = SectionDiff()
    dhcp_servers: SectionDiff = SectionDiff()
    dns: SectionDiff = SectionDiff()
    users: SectionDiff = SectionDiff()
    groups: SectionDiff = SectionDiff()
    authservers: SectionDiff = SectionDiff()
    unrecognized_sections: SectionDiff = SectionDiff()
    # Top-level scalar meta (config_version) — tiny, so we inline it.
    config_version: SectionDiff = SectionDiff()


def diff_configs(a: ParsedConfig, b: ParsedConfig) -> ConfigDiff:
    """Produce a per-section diff between two parsed configs."""
    return ConfigDiff(
        system=_diff_optional_model(a.system, b.system, "system"),
        revision=_diff_optional_model(a.revision, b.revision, "revision"),
        sysctl=_diff_list(a.sysctl, b.sysctl, key="tunable", label_fn=_label_sysctl),
        cron=_diff_list(a.cron, b.cron, key="key", label_fn=_label_cron),
        interfaces=_diff_list(
            a.interfaces, b.interfaces, key="key", label_fn=_label_interface
        ),
        gateways=_diff_list(a.gateways, b.gateways, key="name", label_fn=_label_named),
        gateway_groups=_diff_list(
            a.gateway_groups, b.gateway_groups, key="name", label_fn=_label_named
        ),
        static_routes=_diff_list(
            a.static_routes, b.static_routes, key="key", label_fn=_label_route
        ),
        firewall_rules=_diff_list(
            a.firewall_rules,
            b.firewall_rules,
            key="key",
            label_fn=_label_firewall,
            order_sensitive=True,
        ),
        nat_rules=_diff_list(
            a.nat_rules,
            b.nat_rules,
            key="key",
            label_fn=_label_nat,
            order_sensitive=True,
        ),
        aliases=_diff_list(a.aliases, b.aliases, key="name", label_fn=_label_named),
        dhcp_servers=_diff_list(
            a.dhcp_servers, b.dhcp_servers, key="interface", label_fn=_label_dhcp
        ),
        dns=_diff_optional_model(a.dns, b.dns, "dns"),
        users=_diff_list(a.users, b.users, key="name", label_fn=_label_named),
        groups=_diff_list(a.groups, b.groups, key="name", label_fn=_label_named),
        authservers=_diff_list(
            a.authservers, b.authservers, key="name", label_fn=_label_named
        ),
        unrecognized_sections=_diff_list(
            a.unrecognized_sections,
            b.unrecognized_sections,
            key="tag",
            label_fn=lambda m: m["tag"],
        ),
        config_version=_diff_scalar(
            a.config_version, b.config_version, "config_version"
        ),
    )


# ---------- label helpers ---------------------------------------------------


def _label_named(m: dict[str, Any]) -> str:
    return str(m.get("name") or m.get("key") or "?")


def _label_sysctl(m: dict[str, Any]) -> str:
    return str(m.get("tunable") or "?")


def _label_cron(m: dict[str, Any]) -> str:
    cmd = m.get("command") or ""
    time = " ".join(str(m.get(f) or "*") for f in ("minute", "hour", "mday", "month", "wday"))
    return f"{time}  {cmd}".strip()


def _label_interface(m: dict[str, Any]) -> str:
    key = m.get("key") or ""
    descr = m.get("descr")
    return f"{key} ({descr})" if descr else str(key)


def _label_firewall(m: dict[str, Any]) -> str:
    iface = m.get("interface") or "?"
    action = m.get("type") or "?"
    descr = m.get("descr") or ""
    return f"[{iface}] {action}: {descr}".strip()


def _label_nat(m: dict[str, Any]) -> str:
    kind = m.get("kind") or "?"
    iface = m.get("interface") or "?"
    descr = m.get("descr") or ""
    return f"[{kind} / {iface}] {descr}".strip()


def _label_route(m: dict[str, Any]) -> str:
    return f"{m.get('network') or '?'} via {m.get('gateway') or '?'}"


def _label_dhcp(m: dict[str, Any]) -> str:
    return f"DHCP: {m.get('interface') or '?'}"


# ---------- building blocks -------------------------------------------------


def _dump(model: Any) -> dict[str, Any]:
    """Pydantic -> dict, safely. Falls through for already-dict inputs."""
    if hasattr(model, "model_dump"):
        dumped: dict[str, Any] = model.model_dump()
        return dumped
    if isinstance(model, dict):
        return dict(model)
    raise TypeError(f"cannot dump non-model {type(model)}")


def _diff_scalar(a: Any, b: Any, field: str) -> SectionDiff:
    if a == b:
        return SectionDiff(unchanged_count=1)
    return SectionDiff(
        modified=[
            ItemDiff(
                key=field,
                label=field,
                changes=[FieldChange(field=field, before=a, after=b)],
            )
        ]
    )


def _diff_optional_model(a: Any, b: Any, label: str) -> SectionDiff:
    """Diff two optional Pydantic models as a single pseudo-item."""
    if a is None and b is None:
        return SectionDiff()
    if a is None and b is not None:
        return SectionDiff(added=[_dump(b)])
    if a is not None and b is None:
        return SectionDiff(removed=[_dump(a)])
    changes = _field_changes(_dump(a), _dump(b))
    if not changes:
        return SectionDiff(unchanged_count=1)
    return SectionDiff(modified=[ItemDiff(key=label, label=label, changes=changes)])


def _diff_list(
    a: list[Any],
    b: list[Any],
    *,
    key: str,
    label_fn: Callable[[dict[str, Any]], str],
    order_sensitive: bool = False,
) -> SectionDiff:
    """Diff two lists of Pydantic items keyed by ``key``."""
    a_dump = [_dump(x) for x in a]
    b_dump = [_dump(x) for x in b]
    a_by: dict[str, dict[str, Any]] = {str(d.get(key)): d for d in a_dump}
    b_by: dict[str, dict[str, Any]] = {str(d.get(key)): d for d in b_dump}

    added = [b_by[k] for k in b_by.keys() - a_by.keys()]
    removed = [a_by[k] for k in a_by.keys() - b_by.keys()]

    modified: list[ItemDiff] = []
    reordered: list[ReorderEvent] = []
    unchanged = 0

    a_index = {str(d.get(key)): i for i, d in enumerate(a_dump)}
    b_index = {str(d.get(key)): i for i, d in enumerate(b_dump)}

    for k in a_by.keys() & b_by.keys():
        changes = _field_changes(a_by[k], b_by[k])
        if changes:
            modified.append(
                ItemDiff(key=k, label=label_fn(b_by[k]), changes=changes)
            )
        else:
            unchanged += 1
        if order_sensitive and a_index[k] != b_index[k]:
            reordered.append(
                ReorderEvent(
                    key=k,
                    label=label_fn(b_by[k]),
                    old_index=a_index[k],
                    new_index=b_index[k],
                )
            )

    # Sort for deterministic output (keeps tests and UI stable).
    added.sort(key=lambda d: str(d.get(key)))
    removed.sort(key=lambda d: str(d.get(key)))
    modified.sort(key=lambda m: m.key)
    reordered.sort(key=lambda r: r.new_index)

    return SectionDiff(
        added=added,
        removed=removed,
        modified=modified,
        reordered=reordered,
        unchanged_count=unchanged,
    )


def _field_changes(
    a: dict[str, Any], b: dict[str, Any], prefix: str = ""
) -> list[FieldChange]:
    """Recursively compare two dicts. Keys missing on either side count."""
    out: list[FieldChange] = []
    for k in sorted(a.keys() | b.keys()):
        av = a.get(k)
        bv = b.get(k)
        field = f"{prefix}{k}"
        if av == bv:
            continue
        if isinstance(av, dict) and isinstance(bv, dict):
            out.extend(_field_changes(av, bv, prefix=f"{field}."))
            continue
        out.append(FieldChange(field=field, before=av, after=bv))
    return out
