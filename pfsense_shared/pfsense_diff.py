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
    vlans: SectionDiff = SectionDiff()
    bridges: SectionDiff = SectionDiff()
    gifs: SectionDiff = SectionDiff()
    gres: SectionDiff = SectionDiff()
    ppps: SectionDiff = SectionDiff()
    qinqs: SectionDiff = SectionDiff()
    wol: SectionDiff = SectionDiff()
    gateways: SectionDiff = SectionDiff()
    gateway_groups: SectionDiff = SectionDiff()
    static_routes: SectionDiff = SectionDiff()
    virtual_ips: SectionDiff = SectionDiff()
    hasync: SectionDiff = SectionDiff()
    firewall_rules: SectionDiff = SectionDiff()
    nat_rules: SectionDiff = SectionDiff()
    aliases: SectionDiff = SectionDiff()
    dhcp_servers: SectionDiff = SectionDiff()
    dhcp_relays: SectionDiff = SectionDiff()
    dns: SectionDiff = SectionDiff()
    ntpd: SectionDiff = SectionDiff()
    snmpd: SectionDiff = SectionDiff()
    syslog: SectionDiff = SectionDiff()
    schedules: SectionDiff = SectionDiff()
    shaper_queues: SectionDiff = SectionDiff()
    dnshaper_pipes: SectionDiff = SectionDiff()
    lb_pools: SectionDiff = SectionDiff()
    lb_virtual_servers: SectionDiff = SectionDiff()
    captive_portal_zones: SectionDiff = SectionDiff()
    openvpn_servers: SectionDiff = SectionDiff()
    openvpn_clients: SectionDiff = SectionDiff()
    openvpn_cscs: SectionDiff = SectionDiff()
    ipsec_phase1: SectionDiff = SectionDiff()
    ipsec_phase2: SectionDiff = SectionDiff()
    ipsec_psks: SectionDiff = SectionDiff()
    certificate_authorities: SectionDiff = SectionDiff()
    certificates: SectionDiff = SectionDiff()
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
        vlans=_diff_list(a.vlans, b.vlans, key="key", label_fn=_label_named),
        bridges=_diff_list(
            a.bridges, b.bridges, key="bridgeif", label_fn=_label_bridge
        ),
        gifs=_diff_list(a.gifs, b.gifs, key="name", label_fn=_label_tunnel),
        gres=_diff_list(a.gres, b.gres, key="name", label_fn=_label_tunnel),
        ppps=_diff_list(a.ppps, b.ppps, key="ptpid", label_fn=_label_ppp),
        qinqs=_diff_list(a.qinqs, b.qinqs, key="key", label_fn=_label_named),
        wol=_diff_list(a.wol, b.wol, key="mac", label_fn=_label_wol),
        gateways=_diff_list(a.gateways, b.gateways, key="name", label_fn=_label_named),
        gateway_groups=_diff_list(
            a.gateway_groups, b.gateway_groups, key="name", label_fn=_label_named
        ),
        static_routes=_diff_list(
            a.static_routes, b.static_routes, key="key", label_fn=_label_route
        ),
        virtual_ips=_diff_list(
            a.virtual_ips, b.virtual_ips, key="key", label_fn=_label_vip
        ),
        hasync=_diff_optional_model(a.hasync, b.hasync, "hasync"),
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
        dhcp_relays=_diff_list(
            a.dhcp_relays, b.dhcp_relays, key="kind", label_fn=_label_dhcp_relay
        ),
        dns=_diff_optional_model(a.dns, b.dns, "dns"),
        ntpd=_diff_optional_model(a.ntpd, b.ntpd, "ntpd"),
        snmpd=_diff_optional_model(a.snmpd, b.snmpd, "snmpd"),
        syslog=_diff_optional_model(a.syslog, b.syslog, "syslog"),
        schedules=_diff_list(
            a.schedules, b.schedules, key="name", label_fn=_label_named
        ),
        shaper_queues=_diff_list(
            a.shaper_queues, b.shaper_queues, key="name", label_fn=_label_queue
        ),
        dnshaper_pipes=_diff_list(
            a.dnshaper_pipes, b.dnshaper_pipes, key="name", label_fn=_label_named
        ),
        lb_pools=_diff_list(
            a.lb_pools, b.lb_pools, key="name", label_fn=_label_named
        ),
        lb_virtual_servers=_diff_list(
            a.lb_virtual_servers,
            b.lb_virtual_servers,
            key="name",
            label_fn=_label_named,
        ),
        captive_portal_zones=_diff_list(
            a.captive_portal_zones,
            b.captive_portal_zones,
            key="zone",
            label_fn=_label_portal,
        ),
        openvpn_servers=_diff_list(
            a.openvpn_servers,
            b.openvpn_servers,
            key="vpnid",
            label_fn=_label_ovpn,
        ),
        openvpn_clients=_diff_list(
            a.openvpn_clients,
            b.openvpn_clients,
            key="vpnid",
            label_fn=_label_ovpn,
        ),
        openvpn_cscs=_diff_list(
            a.openvpn_cscs,
            b.openvpn_cscs,
            key="common_name",
            label_fn=_label_csc,
        ),
        ipsec_phase1=_diff_list(
            a.ipsec_phase1,
            b.ipsec_phase1,
            key="ikeid",
            label_fn=_label_ipsec_p1,
        ),
        ipsec_phase2=_diff_list(
            a.ipsec_phase2,
            b.ipsec_phase2,
            key="uniqid",
            label_fn=_label_ipsec_p2,
        ),
        ipsec_psks=_diff_list(
            a.ipsec_psks,
            b.ipsec_psks,
            key="key",
            label_fn=_label_ipsec_psk,
        ),
        certificate_authorities=_diff_list(
            a.certificate_authorities,
            b.certificate_authorities,
            key="refid",
            label_fn=_label_pki,
        ),
        certificates=_diff_list(
            a.certificates,
            b.certificates,
            key="refid",
            label_fn=_label_pki,
        ),
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


def _label_bridge(m: dict[str, Any]) -> str:
    name = m.get("bridgeif") or "?"
    members = m.get("members") or []
    return f"{name} ({', '.join(members) if members else 'no members'})"


def _label_tunnel(m: dict[str, Any]) -> str:
    kind = m.get("kind") or "?"
    name = m.get("name") or "?"
    remote = m.get("remote_addr") or "?"
    return f"[{kind}] {name} → {remote}"


def _label_ppp(m: dict[str, Any]) -> str:
    kind = m.get("type") or "?"
    ifname = m.get("if_") or m.get("ptpid") or "?"
    return f"[{kind}] {ifname}"


def _label_wol(m: dict[str, Any]) -> str:
    iface = m.get("interface") or ""
    descr = m.get("descr") or ""
    suffix = " — ".join(x for x in (iface, descr) if x)
    return f"{m.get('mac') or '?'}{' — ' + suffix if suffix else ''}"


def _label_dhcp_relay(m: dict[str, Any]) -> str:
    kind = m.get("kind") or "?"
    ifs = m.get("interface") or []
    servers = m.get("server") or []
    return f"dhcrelay [{kind}] if={','.join(ifs) or '?'} → {','.join(servers) or '?'}"


def _label_queue(m: dict[str, Any]) -> str:
    iface = m.get("interface") or ""
    name = m.get("name") or "?"
    return f"{name} ({iface})" if iface else name


def _label_portal(m: dict[str, Any]) -> str:
    zone = m.get("zone") or "?"
    ifaces = m.get("interfaces") or []
    return f"{zone} on {','.join(ifaces) or '?'}"


def _label_ovpn(m: dict[str, Any]) -> str:
    desc = m.get("description") or ""
    mode = m.get("mode") or "?"
    vpnid = m.get("vpnid") or "?"
    return f"[{mode}] {desc or '#' + str(vpnid)}"


def _label_csc(m: dict[str, Any]) -> str:
    cn = m.get("common_name") or "?"
    desc = m.get("description") or ""
    return f"{cn}{' — ' + desc if desc else ''}"


def _label_ipsec_p1(m: dict[str, Any]) -> str:
    iketype = m.get("iketype") or "?"
    remote = m.get("remote_gateway") or "?"
    descr = m.get("descr") or ""
    return f"[{iketype}] {remote}{' — ' + descr if descr else ''}"


def _label_ipsec_p2(m: dict[str, Any]) -> str:
    ikeid = m.get("ikeid") or "?"
    mode = m.get("mode") or "?"
    descr = m.get("descr") or ""
    return f"phase2 ikeid={ikeid} [{mode}]{' — ' + descr if descr else ''}"


def _label_ipsec_psk(m: dict[str, Any]) -> str:
    return f"{m.get('ident_type') or '?'}:{m.get('ident') or '?'}"


def _label_pki(m: dict[str, Any]) -> str:
    descr = m.get("descr") or m.get("refid") or "?"
    t = m.get("type")
    return f"[{t}] {descr}" if t else str(descr)


def _label_vip(m: dict[str, Any]) -> str:
    mode = m.get("mode") or "?"
    iface = m.get("interface") or "?"
    subnet = m.get("subnet") or "?"
    vhid = m.get("vhid")
    vhid_str = f" vhid={vhid}" if vhid else ""
    return f"[{mode}] {iface} {subnet}{vhid_str}"


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
