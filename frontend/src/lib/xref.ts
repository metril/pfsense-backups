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

import type { ParsedConfig } from "@/api/parsedTypes";
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
  | "ipsec_phase1"
  | "haproxy_backend"
  | "lb_pool"
  | "user"
  | "group";

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
  ipsec_phase1: "vpn-pki",
  haproxy_backend: "packages",
  lb_pool: "services",
  user: "vpn-pki",
  group: "vpn-pki",
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
    "ipsec_phase1",
    "haproxy_backend",
    "lb_pool",
    "user",
    "group",
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
  return t;
}

/** Build the xref index from a parsed config. Runs in O(refs). */
export function buildIndex(cfg: ParsedConfig): XrefIndex {
  const idx: XrefIndex = { byKind: emptyByKind(), incoming: new Map() };

  // Interfaces — the parser exposes ``key`` as the pfSense-internal
  // name (wan / lan / opt1); ``descr`` is the friendly label.
  for (const i of cfg.interfaces) {
    add(idx, "interface", i.key, i.descr ?? i.key.toUpperCase(), i.if_);
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

  for (const p of cfg.ipsec_phase1) {
    add(
      idx,
      "ipsec_phase1",
      p.ikeid,
      p.descr ?? `IPsec P1 #${p.ikeid}`,
      p.remote_gateway,
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
    const self: XrefTarget = {
      kind: "interface", // placeholder "from" — callers don't render back
      key: r.key,
      label: r.descr ?? `rule ${r.key}`,
      anchorId: `xref-rule-${r.key.replace(/[^A-Za-z0-9_-]/g, "_")}`,
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
  const cardId = enclosingSectionId(id);
  if (cardId) {
    window.dispatchEvent(
      new CustomEvent("pfsense-snap-to-card", { detail: { cardId } }),
    );
  }
  // Defer scroll one frame so a just-opened card has mounted its
  // children before we try to find the anchor.
  requestAnimationFrame(() => scrollAndFlash(id));
}

/** Sugar for callers that want the raw href without importing itemId. */
export function xrefHref(kind: RefKind, key: string): string {
  return `#${itemId(kind, key)}`;
}
