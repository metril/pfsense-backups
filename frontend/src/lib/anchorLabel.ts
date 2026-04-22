/**
 * Human-label helpers for anchor ids.
 *
 * The blame tooltip + drawer both need to translate
 * ``xref-rule-tracker_1706288423`` → something operators can scan
 * ("Firewall rule · allow lan"). This module is the single source
 * of truth for that translation on the frontend; the scope names
 * are kept in lockstep with
 * ``pfsense_shared/anchor_events.py:SECTION_SPEC`` via a backend
 * lint test (``test_frontend_scope_labels_cover_section_spec``).
 */

/** Anchor-id grammar:
 *   ``xref-<scope>-<tail>``    — row under a list section
 *   ``field-<scope>-<tail>``   — single field in a singleton
 *   ``section-<scope>``        — whole singleton section (rare)
 */
export type AnchorNamespace = "xref" | "field" | "section";

/** Parsed anchor id. ``tail`` is ``null`` for ``section-*`` anchors
 *  (or malformed ids with no tail segment). */
export interface ParsedAnchor {
  ns: AnchorNamespace;
  scope: string;
  tail: string | null;
}

// Matches ``pfsense_shared/anchor_events.py:_ANCHOR_RE`` exactly.
// Scope is a single ``[A-Za-z0-9_]+`` segment; the remainder (after
// the first dash) is the tail. Handles keys containing hyphens, e.g.
// ``xref-rule-tracker_fw-rule-42``.
const ANCHOR_RE = /^(xref|field|section)-([A-Za-z0-9_]+?)(?:-(.+))?$/;

export function parseAnchorId(id: string): ParsedAnchor | null {
  const m = ANCHOR_RE.exec(id);
  if (!m) return null;
  return {
    ns: m[1] as AnchorNamespace,
    scope: m[2],
    tail: m[3] ?? null,
  };
}

// Inverse of ``anchor_events.SECTION_SPEC`` + ``PACKAGE_ROW_SPEC`` +
// ``SINGLETON_SPEC``. Keep this table sorted alphabetically by key
// so drift vs. the backend is easy to eyeball during review.
//
// Backend lint: ``tests/pfsense_shared/test_anchor_events.py::
// test_frontend_scope_labels_cover_section_spec`` asserts every
// anchor_kind from ``SECTION_SPEC`` appears here.
export const SECTION_LABELS: Record<string, string> = {
  // Row-shaped anchors (SECTION_SPEC kinds).
  alias: "Alias",
  authserver: "Auth server",
  ca: "Certificate authority",
  cert: "Certificate",
  crl: "Certificate revocation list",
  gateway: "Gateway",
  gateway_group: "Gateway group",
  group: "Group",
  haproxy_backend: "HAProxy backend",
  interface: "Interface",
  interface_group: "Interface group",
  ipsec_phase1: "IPsec phase 1",
  ipsec_phase2: "IPsec phase 2",
  lb_pool: "Load-balancer pool",
  nat: "NAT rule",
  openvpn_client: "OpenVPN client",
  openvpn_csc: "OpenVPN CSC",
  openvpn_server: "OpenVPN server",
  rule: "Firewall rule",
  schedule: "Schedule",
  user: "User",
  vlan: "VLAN",
  // Singleton sections (SINGLETON_SPEC scopes).
  diag: "Diagnostics",
  dns: "DNS",
  ftpproxy: "FTP proxy",
  hasync: "HA sync",
  notifications: "Notifications",
  ntpd: "NTP",
  snmpd: "SNMP",
  syslog: "Syslog",
  system: "System",
  theme: "Theme",
  ups: "UPS",
  // Singleton scope aliases exposed via ``_FIELD_ALIASES`` —
  // anchors emitted under these scopes by the positions map /
  // frontend fieldId calls still route to a ``DnsConfig`` record
  // server-side. Kept here so the tooltip shows "DNS · unbound"
  // instead of the raw scope.
  unbound: "DNS (unbound)",
  // Package singletons (PACKAGE_SINGLETON_SPEC scopes).
  avahi: "Avahi",
  miniupnpd: "UPnP/NAT-PMP",
  openvpn_client_export: "OpenVPN client export",
  telegraf: "Telegraf",
};

export function sectionLabel(scope: string): string {
  // Fallback: capitalise the raw scope so operators see *something*
  // rather than a blank section chip on a new/unknown kind.
  return (
    SECTION_LABELS[scope] ??
    scope.charAt(0).toUpperCase() + scope.slice(1).replace(/_/g, " ")
  );
}

/** Row-valued anchor summaries ship as dicts. Operators recognise
 *  rules / aliases / certs by different fields — pick the best
 *  available one. */
const ROW_LABEL_FIELDS = [
  "descr",
  "name",
  "ifname",
  "common_name",
  "refid",
  "vpnid",
  "ikeid",
  "uniqid",
  "vlanif",
  "key",
] as const;

function pickRowLabel(value: Record<string, unknown>): string | null {
  for (const field of ROW_LABEL_FIELDS) {
    const v = value[field];
    if (typeof v === "string" && v.trim() !== "") return v;
  }
  return null;
}

/** Best-effort human label for a specific anchor given its blame
 *  summary value. Falls back to the anchor id so the caller always
 *  has something to render.
 *
 *  Shapes:
 *   - Row anchor (``xref-rule-xxx``) with dict value →
 *     ``"Firewall rule · allow lan"``
 *   - Field anchor (``field-system-hostname``) →
 *     ``"System · hostname"``
 *   - Section anchor (``section-system``) →
 *     ``"System"``
 *   - Unknown / unresolved → the raw anchor id
 */
export function anchorHumanLabel(
  anchorId: string,
  value?: Record<string, unknown> | string | null,
): string {
  const parsed = parseAnchorId(anchorId);
  if (!parsed) return anchorId;
  const section = sectionLabel(parsed.scope);

  if (parsed.ns === "section") return section;

  if (parsed.ns === "field") {
    return parsed.tail ? `${section} · ${parsed.tail}` : section;
  }

  // xref (row)
  if (value && typeof value === "object") {
    const rowLabel = pickRowLabel(value as Record<string, unknown>);
    if (rowLabel) return `${section} · ${rowLabel}`;
  }
  return parsed.tail ? `${section} · ${parsed.tail}` : section;
}
