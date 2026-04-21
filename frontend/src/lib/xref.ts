/**
 * Cross-reference index for the structured config viewer.
 *
 * Problem: the parsed view surfaces a firewall rule as ``on interface lan``,
 * an OpenVPN server as ``caref: ca_5fa0c4``, a static route as
 * ``gateway WAN_DHCP`` — but clicking those strings does nothing. Operators
 * want to jump to the referenced object and back.
 *
 * This module builds a client-side index once per ``ParsedConfig`` and
 * resolves a ``(kind, key) → XrefTarget`` lookup in O(1). The ``Xref`` chip
 * renders as a proper ``<a href="#xref-{kind}-{key}">`` so keyboard
 * navigation works without JS; the anchor id is applied to the referenced
 * row via ``itemId(kind, key)``.
 *
 * Server-side resolution was considered and rejected — the wire format
 * stays stable, and adding a new edge is a one-line change to the edge
 * table in this file.
 */

import type { Endpoint, NatRule, ParsedConfig } from "@/api/parsedTypes";
import type { SectionGroup } from "@/lib/sectionGroup";

/** Every kind of referenceable object in a pfSense config. */
export type RefKind =
  | "interface"
  | "interface_group"
  | "gateway"
  | "gateway_group"
  | "schedule"
  | "alias"
  | "ca"
  | "cert"
  | "crl"
  | "authserver"
  | "openvpn_server"
  | "openvpn_client"
  | "openvpn_csc"
  | "ipsec_phase1"
  | "ipsec_phase2"
  | "haproxy_backend"
  | "lb_pool"
  | "user"
  | "group"
  // v0.18.0: VLAN definitions. Referenced via the ``vlanif`` key
  // (e.g. ``"em0.100"``) from child interfaces that use the VLAN
  // as their parent_if.
  | "vlan";

/** The section group a target belongs to (for chip coloring). */
const KIND_TO_GROUP: Record<RefKind, SectionGroup> = {
  interface: "networking",
  interface_group: "networking",
  gateway: "networking",
  gateway_group: "networking",
  schedule: "security",
  alias: "security",
  ca: "vpn-pki",
  cert: "vpn-pki",
  crl: "vpn-pki",
  authserver: "vpn-pki",
  openvpn_server: "vpn-pki",
  openvpn_client: "vpn-pki",
  openvpn_csc: "vpn-pki",
  ipsec_phase1: "vpn-pki",
  ipsec_phase2: "vpn-pki",
  haproxy_backend: "packages",
  lb_pool: "services",
  user: "vpn-pki",
  group: "vpn-pki",
  vlan: "networking",
};

export interface XrefTarget {
  kind: RefKind;
  key: string;
  /** Human-readable hover preview. */
  label: string;
  /** DOM id to scroll to. */
  anchorId: string;
  /** Section group, for chip color. */
  group: SectionGroup;
  /** Optional secondary descriptor for the tooltip (descr, CN, etc.). */
  secondary?: string;
}

export interface XrefIndex {
  byKind: Record<RefKind, Map<string, XrefTarget>>;
  /** Reverse index: anchorId → every other target that points at it.
   *  Used by the tooltip to say "Used by N other items." */
  incoming: Map<string, XrefTarget[]>;
  /** ``anchorId → XrefTarget`` lookup. Added in v0.31.0 so
   *  ``findTargetByAnchorId`` is O(1) instead of scanning every
   *  ``byKind`` entry on every back-pill click. Populated at
   *  ``buildIndex`` time — one extra ``Map.set`` per entry. */
  byAnchorId: Map<string, XrefTarget>;
  /** Human labels for leaf rows that aren't proper xref targets —
   *  firewall rules and NAT rules anchored via ``rowAnchorId``. Keyed
   *  by anchorId, value is the row's description (or a sensible
   *  fallback derived from its shape). Used exclusively by the
   *  xref back-navigation stack so the floating pill reads
   *  ``Back to rule: Block Tor exit nodes`` rather than
   *  ``Back to rule: 1706288423_0``. */
  originLabels: Map<string, string>;
}

/** Build a stable DOM id for a referenceable row. */
export function itemId(kind: RefKind, key: string): string {
  // Normalise non-ident chars so the id is a valid CSS selector and
  // fragment URI. pfSense keys can contain ``:``, ``|``, ``/``, ``.``.
  const safe = key.replace(/[^A-Za-z0-9_-]/g, "_");
  return `xref-${kind}-${safe}`;
}

/** Build a stable DOM id for a row that is NOT a cross-ref target
 *  (leaf nodes like firewall rules and NAT rules). Keeps RefKind
 *  focused on actually-referenceable objects while still giving
 *  these rows deep-linkable anchors. */
export function rowAnchorId(scope: "rule" | "nat", key: string): string {
  const safe = key.replace(/[^A-Za-z0-9_-]/g, "_");
  return `xref-${scope}-${safe}`;
}

/** Build a stable DOM id for a single field inside a singleton
 *  panel (``<system><hostname>…``, ``<dnsmasq><enable>…``, …). Emitted
 *  as ``id`` on the ``<dt>`` element of the rendered ``Dl`` row so
 *  the Structured ↔ Raw XML tab-switch sync (v0.22.0) can track
 *  which field the operator is reading. ``section`` must match the
 *  key the backend uses in ``pfsense_shared/pfsense_positions.py``
 *  (``system``, ``dns``, ``ntpd``, ``snmpd``, ``syslog``,
 *  ``notifications``, ``ups``, ``ftpproxy``, ``hasync``, ``avahi``,
 *  ``miniupnpd``, ``openvpn_client_export``, ``telegraf``). */
export function fieldId(section: string, name: string): string {
  const safe = name.replace(/[^A-Za-z0-9_-]/g, "_");
  return `field-${section}-${safe}`;
}

function emptyByKind(): Record<RefKind, Map<string, XrefTarget>> {
  const kinds: RefKind[] = [
    "interface",
    "interface_group",
    "gateway",
    "gateway_group",
    "schedule",
    "alias",
    "ca",
    "cert",
    "crl",
    "authserver",
    "openvpn_server",
    "openvpn_client",
    "openvpn_csc",
    "ipsec_phase1",
    "ipsec_phase2",
    "haproxy_backend",
    "lb_pool",
    "user",
    "group",
    "vlan",
  ];
  return Object.fromEntries(kinds.map((k) => [k, new Map()])) as Record<
    RefKind,
    Map<string, XrefTarget>
  >;
}

function add(
  idx: XrefIndex,
  kind: RefKind,
  key: string | null | undefined,
  label: string,
  secondary?: string | null,
): XrefTarget | null {
  if (!key) return null;
  const t: XrefTarget = {
    kind,
    key,
    label,
    anchorId: itemId(kind, key),
    group: KIND_TO_GROUP[kind],
    secondary: secondary ?? undefined,
  };
  idx.byKind[kind].set(key, t);
  // Populate the reverse index so ``findTargetByAnchorId`` is O(1)
  // — it was scanning every kind map on every back-pill click, which
  // on a large config (1000+ aliases + rules) produced a noticeable
  // lag on rapid back-stack navigation.
  idx.byAnchorId.set(t.anchorId, t);
  return t;
}

/** Render an ``Endpoint`` as the compact ``host[:port]`` form used by
 *  the NAT origin-label fallbacks. ``any`` shows as ``any``; a
 *  negated endpoint gets a leading ``!``. Keeps the output short
 *  enough to fit inside the back-nav pill. */
function endpointCompact(e: Endpoint): string {
  const bang = e.not_ ? "!" : "";
  if (e.any_) return `${bang}any`;
  const host = e.network ?? e.address ?? "?";
  const port = e.port ? `:${e.port}` : "";
  return `${bang}${host}${port}`;
}

/** Describe a NAT rule in a single line when the operator hasn't
 *  supplied a ``<descr>``. Format depends on the kind so the label
 *  matches the mental model for that NAT shape:
 *   - ``port_forward``: ``{proto} {dst} → {target}:{local_port} on {iface}``
 *   - ``one_to_one``:   ``{src} ↔ {target} on {iface}``
 *   - ``outbound``:     ``{src} → {target} on {iface}``
 */
function natFallbackLabel(n: NatRule): string {
  const iface = n.interface ? ` on ${n.interface}` : "";
  const proto = n.protocol ? `${n.protocol} ` : "";
  const target = n.target ?? "?";
  if (n.kind === "port_forward") {
    const dst = endpointCompact(n.destination);
    const lport = n.local_port ? `:${n.local_port}` : "";
    return `${proto}${dst} → ${target}${lport}${iface}`;
  }
  if (n.kind === "one_to_one") {
    const src = endpointCompact(n.source);
    return `${src} ↔ ${target}${iface}`;
  }
  if (n.kind === "outbound") {
    const src = endpointCompact(n.source);
    return `${proto}${src} → ${target}${iface}`;
  }
  return `NAT ${n.key}`;
}

/** Build the xref index from a parsed config. Runs in O(refs). */
export function buildIndex(cfg: ParsedConfig): XrefIndex {
  const idx: XrefIndex = {
    byKind: emptyByKind(),
    incoming: new Map(),
    byAnchorId: new Map(),
    originLabels: new Map(),
  };

  // Interfaces — the parser exposes ``key`` as the pfSense-internal
  // name (wan / lan / opt1); ``descr`` is the friendly label.
  for (const i of cfg.interfaces) {
    add(idx, "interface", i.key, i.descr ?? i.key.toUpperCase(), i.if_);
  }

  // VLANs — keyed by the vlanif string (e.g. ``em0.100``). Operators
  // jump here when a child interface's parent_if matches a VLAN
  // definition. Secondary descriptor carries tag + parent for
  // tooltip scannability.
  for (const v of cfg.vlans) {
    if (!v.vlanif) continue;
    add(
      idx,
      "vlan",
      v.vlanif,
      v.descr ?? v.vlanif,
      v.tag ? `tag ${v.tag}${v.if_ ? ` on ${v.if_}` : ""}` : v.if_ ?? undefined,
    );
  }

  // Interface groups — firewall rules can target these the same way
  // they target individual interfaces, so they belong in the same
  // jump target vocabulary.
  for (const ig of cfg.interface_groups) {
    add(
      idx,
      "interface_group",
      ig.ifname,
      ig.ifname,
      ig.descr ?? ig.members.join(", "),
    );
  }

  // Gateways — keyed by name; descr makes the tooltip useful.
  for (const g of cfg.gateways) {
    add(idx, "gateway", g.name, g.name, g.descr ?? g.gateway);
  }

  for (const gg of cfg.gateway_groups) {
    add(idx, "gateway_group", gg.name, gg.name, gg.descr);
  }

  for (const s of cfg.schedules) {
    add(idx, "schedule", s.name, s.name, s.descr);
  }

  for (const a of cfg.aliases) {
    add(idx, "alias", a.name, a.name, a.descr ?? a.type);
  }

  for (const ca of cfg.certificate_authorities) {
    add(idx, "ca", ca.refid, ca.descr ?? ca.refid, ca.metadata?.subject_cn);
  }

  for (const c of cfg.certificates) {
    add(idx, "cert", c.refid, c.descr ?? c.refid, c.metadata?.subject_cn);
  }

  for (const crl of cfg.crls) {
    add(idx, "crl", crl.refid, crl.descr ?? crl.refid);
  }

  for (const s of cfg.authservers) {
    add(idx, "authserver", s.name, s.name, s.type);
  }

  for (const ov of cfg.openvpn_servers) {
    add(
      idx,
      "openvpn_server",
      ov.vpnid,
      ov.description ?? `OpenVPN srv #${ov.vpnid}`,
      ov.mode,
    );
  }

  for (const ov of cfg.openvpn_clients) {
    add(
      idx,
      "openvpn_client",
      ov.vpnid,
      ov.description ?? `OpenVPN cli #${ov.vpnid}`,
      ov.server_addr,
    );
  }

  // OpenVPN client-specific overrides — keyed by ``common_name``.
  // Backend already carries a resolver scope for these; aligning the
  // frontend closes the mirror-table gap so the blame drawer can
  // work on ``xref-openvpn_csc-*`` anchors the viewer emits.
  for (const csc of cfg.openvpn_cscs) {
    add(
      idx,
      "openvpn_csc",
      csc.common_name,
      csc.description ?? csc.common_name,
      csc.tunnel_network,
    );
  }

  for (const p of cfg.ipsec_phase1) {
    add(
      idx,
      "ipsec_phase1",
      p.ikeid,
      p.descr ?? `IPsec P1 #${p.ikeid}`,
      p.remote_gateway,
    );
  }

  // IPsec Phase 2 child SAs — keyed by ``uniqid``. Secondary is the
  // protocol + mode so the tooltip is informative even without a descr.
  for (const p2 of cfg.ipsec_phase2) {
    add(
      idx,
      "ipsec_phase2",
      p2.uniqid,
      p2.descr ?? `IPsec P2 #${p2.uniqid}`,
      p2.mode ?? p2.protocol,
    );
  }

  if (cfg.installedpackages?.haproxy) {
    for (const b of cfg.installedpackages.haproxy.backends) {
      add(idx, "haproxy_backend", b.name, b.name, b.descr);
    }
  }

  for (const p of cfg.lb_pools) {
    add(idx, "lb_pool", p.name, p.name, p.descr);
  }

  for (const u of cfg.users) {
    add(idx, "user", u.name, u.name, u.descr ?? u.uid);
  }

  for (const g of cfg.groups) {
    add(idx, "group", g.name, g.name, g.description);
  }

  // Incoming edges — walk every cross-ref in the config. Each entry
  // below corresponds to one edge in the plan's edge inventory.
  const linkFrom = (target: XrefTarget | null, from: XrefTarget | null) => {
    if (!target || !from) return;
    const bucket = idx.incoming.get(target.anchorId) ?? [];
    bucket.push(from);
    idx.incoming.set(target.anchorId, bucket);
  };

  for (const r of cfg.firewall_rules) {
    const anchorId = rowAnchorId("rule", r.key);
    // Prefer the rule's description; fall back to an action + iface
    // summary (``pass on lan``) before the opaque tracker key so the
    // back-nav pill is always somewhat readable.
    const fallback =
      r.interface && r.type
        ? `${r.type} on ${r.interface}`
        : `rule ${r.key}`;
    const label = r.descr ?? fallback;
    idx.originLabels.set(anchorId, label);
    const self: XrefTarget = {
      kind: "interface", // placeholder "from" — callers don't render back
      key: r.key,
      label,
      anchorId,
      group: "security",
    };
    if (r.interface) {
      // Firewall rules can target either a physical interface or a
      // named interface group. Populate incoming edges on both so the
      // group chip's tooltip accurately says "used by N rules".
      linkFrom(idx.byKind.interface.get(r.interface) ?? null, self);
      linkFrom(idx.byKind.interface_group.get(r.interface) ?? null, self);
    }
    if (r.gateway) linkFrom(idx.byKind.gateway.get(r.gateway) ?? null, self);
    if (r.schedule)
      linkFrom(idx.byKind.schedule.get(r.schedule) ?? null, self);
  }

  // NAT rules are deep-link targets (anchored via ``rowAnchorId("nat",
  // key)``) but never referenced in a ``RefKind`` sense, so they only
  // need an origin label for the back-nav pill.
  for (const n of cfg.nat_rules) {
    const anchorId = rowAnchorId("nat", n.key);
    idx.originLabels.set(anchorId, n.descr ?? natFallbackLabel(n));
  }

  return idx;
}

/** Resolve a reference; returns ``null`` if the target doesn't exist. */
export function resolve(
  index: XrefIndex,
  kind: RefKind,
  key: string | null | undefined,
): XrefTarget | null {
  if (!key) return null;
  return index.byKind[kind].get(key) ?? null;
}

/** All targets across all kinds, for the quick-jump palette. */
export function allTargets(index: XrefIndex): XrefTarget[] {
  const out: XrefTarget[] = [];
  for (const m of Object.values(index.byKind)) {
    for (const t of m.values()) out.push(t);
  }
  return out;
}

/** Reverse-lookup by DOM id. Used by the xref back-navigation stack
 *  to resolve a human-readable label for an origin row when the user
 *  clicks a chip inside it. Returns ``null`` for anchor ids that
 *  aren't proper xref targets (leaf rows emitted via ``rowAnchorId``,
 *  e.g. firewall rules / NATs — their labels have to be derived from
 *  the DOM instead). */
export function findTargetByAnchorId(
  index: XrefIndex,
  anchorId: string,
): XrefTarget | null {
  return index.byAnchorId.get(anchorId) ?? null;
}

/** Human label for a leaf row (firewall rule, NAT rule). Returns
 *  ``null`` when the id doesn't correspond to a known leaf — callers
 *  then fall back to parsing the id itself. */
export function findOriginLabel(
  index: XrefIndex,
  anchorId: string,
): string | null {
  return index.originLabels.get(anchorId) ?? null;
}

/** Scroll to an anchor id and play the flash animation. Used by
 *  ``Xref`` click handlers and the QuickJump palette alike. */
export function scrollAndFlash(anchorId: string): void {
  const el = document.getElementById(anchorId);
  if (!el) return;
  el.scrollIntoView({ block: "center", behavior: "smooth" });
  // Re-trigger by removing then re-adding on next frame so repeated
  // clicks on the same target still flash.
  el.classList.remove("xref-flash");
  // Force reflow — `void el.offsetWidth` is the idiomatic way.
  void el.offsetWidth;
  el.classList.add("xref-flash");
  window.setTimeout(() => el.classList.remove("xref-flash"), 1600);
}

/** Given an anchor id, walk up the DOM to find the id of its enclosing
 *  section card — either ``section-*`` (viewer) or ``diff-*`` (diff).
 *  Used by ``expandThenScrollToHash`` to know which Card to auto-open
 *  before scrolling. */
export function enclosingSectionId(anchorId: string): string | null {
  const el = document.getElementById(anchorId);
  if (!el) return null;
  const section = el.closest<HTMLElement>(
    "[id^='section-'], [id^='diff-']",
  );
  return section?.id ?? null;
}

/** Fallback when ``enclosingSectionId`` returns ``null`` because the
 *  target anchor hasn't rendered yet (typical when its Card is
 *  collapsed — Card gates its children on ``open``). Parses an anchor
 *  id of the form ``xref-{kind}-{key}`` or ``xref-rule-…`` /
 *  ``xref-nat-…`` and maps it to the section id the card would carry.
 *
 *  Without this, pasting ``#xref-alias-Foo`` into a new tab where
 *  sessionStorage has the Aliases card marked "closed" is a silent
 *  no-op: the target element isn't in the DOM, so no snap event
 *  fires, so the card never opens, so ``scrollAndFlash`` finds
 *  nothing. With this fallback, the snap event still fires.
 *
 *  Returns ``null`` for ids we don't recognize (e.g. diff anchors
 *  the user pasted manually) — caller falls back gracefully. */
export function sectionIdForAnchor(anchorId: string): string | null {
  if (anchorId.startsWith("section-") || anchorId.startsWith("diff-"))
    return anchorId;
  if (!anchorId.startsWith("xref-")) return null;
  // ``xref-{scope}-{key}`` — scope is the kind OR "rule"/"nat" from
  // ``rowAnchorId``.
  const afterPrefix = anchorId.slice("xref-".length);
  const dash = afterPrefix.indexOf("-");
  if (dash < 0) return null;
  const scope = afterPrefix.slice(0, dash);
  return SCOPE_TO_SECTION_ID[scope] ?? null;
}

/** Maps an xref scope (the ``{kind}`` or ``rule``/``nat`` fragment of
 *  a ``xref-*`` anchor id) to the DOM id of the section card that
 *  renders rows of that kind. Mirrors the section titles in
 *  ``ParsedBackupView.tsx`` (``section-<kebab-title>``). Keep in sync
 *  when a new RefKind is added. */
const SCOPE_TO_SECTION_ID: Record<string, string> = {
  interface: "section-interfaces",
  interface_group: "section-interface-groups",
  gateway: "section-gateways",
  gateway_group: "section-gateway-groups",
  schedule: "section-schedules",
  alias: "section-aliases",
  ca: "section-certificate-authorities",
  cert: "section-certificates",
  crl: "section-certificate-revocation-lists",
  authserver: "section-external-auth-servers",
  openvpn_server: "section-openvpn-servers",
  openvpn_client: "section-openvpn-clients",
  openvpn_csc: "section-openvpn-client-specific-overrides",
  ipsec_phase1: "section-ipsec-phase-1",
  ipsec_phase2: "section-ipsec-phase-2",
  haproxy_backend: "section-installed-packages",
  lb_pool: "section-load-balancer",
  user: "section-users",
  group: "section-groups",
  rule: "section-firewall-rules",
  nat: "section-nat-rules",
  vlan: "section-vlans",
};

/** Entry point for all hash-driven navigation. Given a hash like
 *  ``"#xref-alias-Foo"`` (with or without the leading ``#``):
 *
 *  1. Finds the target element and its enclosing card id.
 *  2. Dispatches a ``pfsense-snap-to-card`` CustomEvent so whatever
 *     CardGroupProvider is mounted can open the right card. Using an
 *     event instead of reaching into React state keeps this helper
 *     framework-free and callable from the ``Xref`` click handler
 *     without prop-drilling the context.
 *  3. Schedules ``scrollAndFlash`` in a microtask so the card has had
 *     a render tick to mount its content before we try to scroll.
 *
 *  Safe to call when the target doesn't exist (no-op) or when no
 *  provider is listening (just scrolls to whatever is already visible).
 */
export function expandThenScrollToHash(hash: string): void {
  const id = hash.startsWith("#") ? hash.slice(1) : hash;
  if (!id) return;
  // Update the URL hash so copy-link works. Replace, don't push —
  // back button shouldn't cycle hash values.
  try {
    history.replaceState(null, "", `#${id}`);
  } catch {
    // ignore (some sandboxed contexts).
  }
  // First try the DOM-ancestor approach — fastest, covers anchors
  // whose card is already open. If that fails (anchor element not
  // rendered because its card is collapsed), fall back to the
  // scope→section-id table so we can still snap the right card open
  // before the retry scroll.
  const cardId = enclosingSectionId(id) ?? sectionIdForAnchor(id);
  if (cardId) {
    window.dispatchEvent(
      new CustomEvent("pfsense-snap-to-card", { detail: { cardId } }),
    );
  }
  // Double-RAF: one frame for React to flush the Card's state update,
  // a second frame for the Card's children to commit before we try
  // to find the anchor. Without this, scrollAndFlash races the snap.
  requestAnimationFrame(() =>
    requestAnimationFrame(() => scrollAndFlash(id)),
  );
}

/** Sugar for callers that want the raw href without importing itemId. */
export function xrefHref(kind: RefKind, key: string): string {
  return `#${itemId(kind, key)}`;
}
