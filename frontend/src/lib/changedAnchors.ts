import type { ConfigDiff } from "@/api/parsedTypes";
import { fieldId, itemId, rowAnchorId, type RefKind } from "@/lib/xref";

/**
 * Walk a ``ConfigDiff`` and emit the set of DOM anchor ids the
 * history viewer should highlight as "changed since the previous
 * backup". Covers three anchor shapes:
 *
 *  - Table rows: ``added`` / ``removed`` / ``modified`` / ``reordered``
 *    entries → ``xref-{kind}-{key}`` or ``xref-{scope}-{key}``.
 *  - Singleton ``modified[].changes[]`` entries → ``field-{section}-
 *    {fieldName}`` for per-field highlighting under System / DNS /
 *    NTP / etc.
 *  - The containing section root (``section-{section}``) whenever ANY
 *    change lands in that section — gives the operator a quick
 *    visual cue that "something changed in here" even before they
 *    drill in.
 */

type Scope = { kind: "refkind"; refKind: RefKind } | { kind: "scope"; name: "rule" | "nat" };

// Map of section-name → (anchor builder for that section's rows, if any).
// Sections whose rows are referenceable live objects use
// ``itemId(kind, key)``; sections whose rows are leaves (firewall
// rules, NATs) use ``rowAnchorId(scope, key)``.
const SECTION_ROW_ANCHOR: Record<string, Scope | null> = {
  // Leaf row sections.
  firewall_rules: { kind: "scope", name: "rule" },
  nat_rules: { kind: "scope", name: "nat" },
  // Referenceable (RefKind) sections.
  interfaces: { kind: "refkind", refKind: "interface" },
  vlans: { kind: "refkind", refKind: "vlan" },
  gateways: { kind: "refkind", refKind: "gateway" },
  gateway_groups: { kind: "refkind", refKind: "gateway_group" },
  schedules: { kind: "refkind", refKind: "schedule" },
  aliases: { kind: "refkind", refKind: "alias" },
  certificate_authorities: { kind: "refkind", refKind: "ca" },
  certificates: { kind: "refkind", refKind: "cert" },
  crls: { kind: "refkind", refKind: "crl" },
  authservers: { kind: "refkind", refKind: "authserver" },
  openvpn_servers: { kind: "refkind", refKind: "openvpn_server" },
  openvpn_clients: { kind: "refkind", refKind: "openvpn_client" },
  ipsec_phase1: { kind: "refkind", refKind: "ipsec_phase1" },
  lb_pools: { kind: "refkind", refKind: "lb_pool" },
  users: { kind: "refkind", refKind: "user" },
  groups: { kind: "refkind", refKind: "group" },
  interface_groups: { kind: "refkind", refKind: "interface_group" },
  // Sections without a stable per-row anchor — only the section-
  // level fallback applies. Listed as ``null`` so we can still
  // surface "something changed here" without producing garbage ids.
  sysctl: null,
  cron: null,
  bridges: null,
  gifs: null,
  gres: null,
  ppps: null,
  qinqs: null,
  laggs: null,
  wol: null,
  static_routes: null,
  virtual_ips: null,
  dhcp_servers: null,
  dhcp_relays: null,
  dyndns_entries: null,
  shaper_queues: null,
  dnshaper_pipes: null,
  lb_virtual_servers: null,
  captive_portal_zones: null,
  igmpproxy_entries: null,
  radvd_interfaces: null,
  ipsec_phase2: null,
  ipsec_psks: null,
  pppoe_servers: null,
  voucher_rolls: null,
  apikeys: null,
  proxyarp: null,
  unrecognized_sections: null,
};

// Sections whose ``modified[].changes[]`` correspond to per-field
// rows in the Structured view. The value is the ``section`` key
// used by ``fieldId(section, field)``.
const SINGLETON_FIELD_SECTION: Record<string, string> = {
  system: "system",
  dns: "dns",
  hasync: "hasync",
  ntpd: "ntpd",
  snmpd: "snmpd",
  syslog: "syslog",
  notifications: "notifications",
  ups: "ups",
  ftpproxy: "ftpproxy",
  diag: "diag",
  // Package singletons mirrored in pfsense_shared/pfsense_positions.py
  // under ``_SINGLETON_SECTIONS``. Sections here that don't also
  // appear there produce orphan ids — the highlight still renders
  // as a no-op (selector matches nothing), harmless.
};

function rowAnchorFor(section: string, key: string): string | null {
  const scope = SECTION_ROW_ANCHOR[section];
  if (!scope) return null;
  if (scope.kind === "scope") return rowAnchorId(scope.name, key);
  return itemId(scope.refKind, key);
}

/** Returns the set of anchor ids considered "changed" between the
 *  pair of backups this diff was computed against. */
export function collectChangedAnchors(diff: ConfigDiff): Set<string> {
  const changed = new Set<string>();
  for (const [section, sectionDiff] of Object.entries(
    diff as unknown as Record<string, unknown>,
  )) {
    if (!sectionDiff || typeof sectionDiff !== "object") continue;
    const sd = sectionDiff as {
      added?: Array<Record<string, unknown>>;
      removed?: Array<Record<string, unknown>>;
      modified?: Array<{ key: string; changes?: Array<{ field: string }> }>;
      reordered?: Array<{ key: string }>;
    };

    // Count any activity in this section as "dirty" so we also mark
    // the section-level anchor. Don't early-return on inactive
    // sections though — we still need to iterate modified to pick
    // up field-level ids for singletons.
    let touched = false;

    for (const item of sd.added ?? []) {
      touched = true;
      const key = typeof item.key === "string" ? item.key : undefined;
      if (key) {
        const a = rowAnchorFor(section, key);
        if (a) changed.add(a);
      }
    }
    for (const item of sd.removed ?? []) {
      touched = true;
      const key = typeof item.key === "string" ? item.key : undefined;
      if (key) {
        const a = rowAnchorFor(section, key);
        if (a) changed.add(a);
      }
    }
    for (const item of sd.reordered ?? []) {
      touched = true;
      const a = rowAnchorFor(section, item.key);
      if (a) changed.add(a);
    }
    for (const item of sd.modified ?? []) {
      touched = true;
      const a = rowAnchorFor(section, item.key);
      if (a) changed.add(a);
      // For singletons, the "key" of the modified item is typically
      // the section name itself (``"system"``) and ``changes[]``
      // lists the actual field diffs.
      const fieldSection = SINGLETON_FIELD_SECTION[section];
      if (fieldSection) {
        for (const c of item.changes ?? []) {
          changed.add(fieldId(fieldSection, c.field));
        }
      }
    }

    if (touched) changed.add(`section-${section}`);
  }
  return changed;
}
