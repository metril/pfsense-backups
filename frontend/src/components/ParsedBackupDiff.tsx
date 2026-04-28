import {
  Fragment,
  useCallback,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Lock } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Alert } from "@/components/ui/Alert";
import { ExpandCollapseAll } from "@/components/ui/ExpandCollapseAll";
import { FilterBar } from "@/components/ui/FilterBar";
import { FilterProvider } from "@/components/ui/FilterContext";
import { FilterHiddenAnchorBanner } from "@/components/ui/FilterHiddenAnchorBanner";
import { Xref } from "@/components/ui/Xref";
import { CardGroupProvider } from "@/components/CardGroupContext";
import { XrefProvider, type XrefSide } from "@/components/xref/XrefContext";
import { Dl, type DlRow } from "@/components/view/primitives";
import { DeepLinkBridge } from "@/components/xref/DeepLinkBridge";
import { useParsedBackup, useParsedDiffPair } from "@/api/queries";
import type { ParsedConfig } from "@/api/parsedTypes";
import { cn } from "@/lib/cn";
import {
  buildMatcher,
  rowHaystack,
  type FilterMatcher,
} from "@/lib/filter";
import { useMediaQuery } from "@/lib/useMediaQuery";
import { useActiveSection } from "@/lib/useActiveSection";
import type { RefKind } from "@/lib/xref";
import {
  groupClasses,
  sectionGroup,
  type SectionGroup,
} from "@/lib/sectionGroup";
import type {
  ConfigDiff,
  FieldChange,
  ItemDiff,
  ReorderEvent,
  SectionDiff,
} from "@/api/parsedTypes";

/** Per-section labels shown in the summary strip + expanded cards.
 *  Keys match ConfigDiff property names one-to-one. ``group`` drives
 *  the summary chip + card stripe color. */
interface SectionLabel {
  key: keyof ConfigDiff;
  label: string;
  group: SectionGroup;
}

function lbl(key: keyof ConfigDiff, label: string): SectionLabel {
  return { key, label, group: sectionGroup(key as string) };
}

const SECTION_LABELS: SectionLabel[] = [
  lbl("config_version", "Config schema"),
  lbl("system", "System"),
  lbl("revision", "Last revision"),
  lbl("interfaces", "Interfaces"),
  lbl("vlans", "VLANs"),
  lbl("bridges", "Bridges"),
  lbl("gifs", "GIF tunnels"),
  lbl("gres", "GRE tunnels"),
  lbl("ppps", "PPP interfaces"),
  lbl("qinqs", "QinQ"),
  lbl("laggs", "LAGG"),
  lbl("wol", "Wake-on-LAN"),
  lbl("virtual_ips", "Virtual IPs / CARP"),
  lbl("hasync", "HA / CARP sync"),
  lbl("gateways", "Gateways"),
  lbl("gateway_groups", "Gateway groups"),
  lbl("static_routes", "Static routes"),
  lbl("firewall_rules", "Firewall rules"),
  lbl("nat_rules", "NAT rules"),
  lbl("aliases", "Aliases"),
  lbl("schedules", "Schedules"),
  lbl("dhcp_servers", "DHCP servers"),
  lbl("dhcp_relays", "DHCP relay"),
  lbl("dns", "DNS"),
  lbl("dyndns_entries", "Dynamic DNS"),
  lbl("igmpproxy_entries", "IGMP proxy"),
  lbl("radvd_interfaces", "Router Advertisements (IPv6)"),
  lbl("notifications", "Notifications"),
  lbl("ups", "UPS monitoring"),
  lbl("voucher_rolls", "Captive-portal vouchers"),
  lbl("ftpproxy", "FTP proxy"),
  lbl("ntpd", "NTP server"),
  lbl("snmpd", "SNMP"),
  lbl("syslog", "Remote syslog"),
  lbl("shaper_queues", "Shaper queues"),
  lbl("dnshaper_pipes", "Limiter pipes"),
  lbl("lb_pools", "LB pools"),
  lbl("lb_virtual_servers", "LB virtual servers"),
  lbl("captive_portal_zones", "Captive portal"),
  lbl("openvpn_servers", "OpenVPN servers"),
  lbl("openvpn_clients", "OpenVPN clients"),
  lbl("openvpn_cscs", "OpenVPN CSOs"),
  lbl("ipsec_phase1", "IPsec phase 1"),
  lbl("ipsec_phase2", "IPsec phase 2"),
  lbl("ipsec_psks", "IPsec PSKs"),
  lbl("certificate_authorities", "CAs"),
  lbl("certificates", "Certificates"),
  lbl("crls", "CRLs"),
  lbl("installedpackages", "Installed packages"),
  lbl("users", "Users"),
  lbl("groups", "Groups"),
  lbl("authservers", "Auth servers"),
  lbl("sysctl", "Sysctl"),
  lbl("cron", "Cron"),
  // v0.14.0
  lbl("lastchange", "Last change"),
  lbl("theme", "Theme"),
  lbl("diag", "Diagnostic prefs"),
  lbl("dhcp_backend", "DHCP backend"),
  lbl("legacy_bridge", "Bridge (legacy)"),
  lbl("proxyarp", "Proxy ARP"),
  lbl("interface_groups", "Interface groups"),
  lbl("ezshaper", "Shaper wizard"),
  lbl("ovpnserver_wizard", "OpenVPN wizard"),
  lbl("apikeys", "API keys"),
  lbl("l2tp", "L2TP server"),
  lbl("pppoe_servers", "PPPoE servers"),
  lbl("sshdata", "SSH host keys"),
  lbl("unrecognized_sections", "Other sections"),
];

/**
 * Per-section field → xrefable-kind map. When a diff row exposes one
 * of these fields with a string value, render it as an ``<Xref>`` chip
 * instead of plain text so the operator can pivot to the referenced
 * definition on the appropriate side's viewer.
 *
 * Fields allowed to chain to multiple kinds (e.g. ``interface`` may be
 * a physical iface OR an interface group) are expressed as an array —
 * kinds are tried left-to-right via nested Xref ``fallback`` props.
 *
 * Only primitive-string fields are covered here. Nested structures
 * (``source.address``, ``destination.address`` on firewall rules) are
 * not unrolled by ``ItemJson`` / ``FieldChanges`` today; promoting
 * those to chips would require walking the object and is out of scope
 * for v0.15.0.
 */
const FIELD_KIND_MAP: Record<string, Record<string, RefKind | RefKind[]>> = {
  firewall_rules: {
    interface: ["interface", "interface_group"],
    interface_to_send_via: ["interface", "interface_group"],
    gateway: ["gateway", "gateway_group"],
    schedule: "schedule",
  },
  nat_rules: {
    interface: ["interface", "interface_group"],
    target: "interface",
  },
  static_routes: {
    gateway: ["gateway", "gateway_group"],
  },
  gateway_groups: {
    // descr + name are the identifying fields — no refs inside.
  },
  dhcp_relays: {
    interface: ["interface", "interface_group"],
  },
  dhcp_servers: {
    interface: ["interface", "interface_group"],
  },
  openvpn_servers: {
    caref: "ca",
    certref: "cert",
    crlref: "crl",
    interface: ["interface", "interface_group"],
  },
  openvpn_clients: {
    caref: "ca",
    certref: "cert",
    interface: ["interface", "interface_group"],
  },
  ipsec_phase1: {
    caref: "ca",
    certref: "cert",
    interface: ["interface", "interface_group"],
  },
  certificates: {
    caref: "ca",
  },
  crls: {
    caref: "ca",
  },
  users: {
    // ``groups`` is a list — handled separately via ValueChip array path.
  },
  interfaces: {
    if_: "interface",
  },
  interface_groups: {
    // members is a list of interface names — handled via ValueChip.
  },
};

function kindsForField(
  sectionKey: string,
  field: string,
): RefKind[] | null {
  const entry = FIELD_KIND_MAP[sectionKey]?.[field];
  if (!entry) return null;
  return Array.isArray(entry) ? entry : [entry];
}

/** Chip-rendering helper. Given a value and a section+field context,
 *  decide whether to render an Xref chip (chain of fallbacks across
 *  multiple kinds) or a plain formatted value. ``side`` picks which
 *  stacked provider resolves the ref. */
function ValueChip({
  sectionKey,
  field,
  value,
  side,
}: {
  sectionKey: string;
  field: string;
  value: unknown;
  side: XrefSide;
}): ReactNode {
  if (typeof value !== "string" || !value) return formatValue(value);
  const kinds = kindsForField(sectionKey, field);
  if (!kinds || kinds.length === 0) return formatValue(value);
  // Chain kinds left-to-right via nested Xref fallbacks — try
  // interface, then interface_group, then plain formatted value.
  const plain = <span className="font-mono">{value}</span>;
  return kinds.reduceRight<ReactNode>(
    (fallback, kind) => (
      <Xref kind={kind} k={value} side={side} fallback={fallback} />
    ),
    plain,
  );
}

function sectionHasChanges(s: SectionDiff): boolean {
  return (
    s.added.length > 0 ||
    s.removed.length > 0 ||
    s.modified.length > 0 ||
    s.reordered.length > 0
  );
}

function changeCount(s: SectionDiff): number {
  return (
    s.added.length + s.removed.length + s.modified.length + s.reordered.length
  );
}

export function ParsedBackupDiff({
  a,
  b,
}: {
  a: number;
  b: number;
}) {
  const { data: rawDiff, error, isLoading } = useParsedDiffPair(a, b);
  // Parallel fetches for the two source configs — xref chips in
  // diff sections resolve against these. TanStack Query dedupes + caches
  // with staleTime: Infinity so a second visit is free.
  // v0.22.0 wrapped the parsed response as ``{config, positions}``;
  // the diff view only needs the config (positions are viewer-only).
  const { data: oldParsed } = useParsedBackup(a);
  const { data: newParsed } = useParsedBackup(b);
  const oldCfg = oldParsed?.config;
  const newCfg = newParsed?.config;

  const [searchParams, setSearchParams] = useSearchParams();
  const filterQuery = searchParams.get("filter") ?? "";
  const setFilterQuery = useCallback(
    (next: string) => {
      setSearchParams(
        (prev) => {
          if (next) prev.set("filter", next);
          else prev.delete("filter");
          return prev;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );
  const matcher = useMemo(() => buildMatcher(filterQuery), [filterQuery]);
  // Narrow every section's added/removed/modified arrays against the
  // filter before rendering. ``sectionHasChanges`` downstream handles
  // hiding sections whose deltas are all filtered out.
  const data = useMemo<ConfigDiff | null>(() => {
    if (!rawDiff) return null;
    if (!matcher.active) return rawDiff;
    return narrowDiff(rawDiff, matcher);
  }, [rawDiff, matcher]);
  const sectionCounter = useMemo(() => {
    if (!rawDiff || !data) return undefined;
    const total = SECTION_LABELS.reduce(
      (n, { key }) => n + (sectionHasChanges(rawDiff[key]) ? 1 : 0),
      0,
    );
    const visible = SECTION_LABELS.reduce(
      (n, { key }) => n + (sectionHasChanges(data[key]) ? 1 : 0),
      0,
    );
    return { visible, total };
  }, [rawDiff, data]);

  if (isLoading)
    return <div className="p-6 text-sm text-muted-fg">Computing diff…</div>;
  if (error)
    return (
      <div className="p-6">
        <Alert tone="danger" title="Could not compute diff">
          {String(error)}
        </Alert>
      </div>
    );
  if (!data || !rawDiff) return null;

  const totalChanges = SECTION_LABELS.reduce(
    (n, { key }) => n + changeCount(data[key]),
    0,
  );

  const sections = (
    <div className="mt-4 space-y-3">
      {SECTION_LABELS.map(({ key, label, group }) => {
        const s = data[key];
        if (!sectionHasChanges(s)) return null;
        return (
          <DiffSectionCard
            key={key}
            id={`diff-${String(key)}`}
            sectionKey={String(key)}
            label={label}
            group={group}
            section={s}
          />
        );
      })}
    </div>
  );

  const emptyBanner =
    totalChanges === 0 ? (
      <Alert
        tone="ok"
        title={matcher.active ? "No matching changes" : "No changes"}
      >
        {matcher.active
          ? "No changes match your filter. Clear it to see the full diff."
          : "No semantic changes detected across any tracked section."}
      </Alert>
    ) : null;

  const body = (
    <FilterProvider query={filterQuery}>
      <CardGroupProvider scope={`diff:${a}-${b}`}>
        <DeepLinkBridge />
        <DiffLayout
          diff={data}
          filterQuery={filterQuery}
          setFilterQuery={setFilterQuery}
          sectionCounter={sectionCounter}
          emptyBanner={emptyBanner}
        >
          {sections}
        </DiffLayout>
      </CardGroupProvider>
    </FilterProvider>
  );

  // Stack dual XrefProviders (old + new) when both configs have
  // arrived. Chips inside diff sections take a ``side`` prop and
  // resolve against the matching provider, producing route-mode
  // hrefs that open the target in the appropriate viewer page.
  // Until both configs arrive, render without providers — chips
  // degrade to plain text (Xref handles the null-index case).
  return (
    <DualXrefProviders oldCfg={oldCfg} newCfg={newCfg} a={a} b={b}>
      {body}
    </DualXrefProviders>
  );
}

function DualXrefProviders({
  oldCfg,
  newCfg,
  a,
  b,
  children,
}: {
  oldCfg: ParsedConfig | undefined;
  newCfg: ParsedConfig | undefined;
  a: number;
  b: number;
  children: ReactNode;
}) {
  if (!oldCfg || !newCfg) return <>{children}</>;
  return (
    <XrefProvider data={oldCfg} side="old" backupId={a} hrefMode="route">
      <XrefProvider data={newCfg} side="new" backupId={b} hrefMode="route">
        {children}
      </XrefProvider>
    </XrefProvider>
  );
}

/** Returns a ``ConfigDiff`` with every section's added / removed /
 *  modified arrays narrowed to entries that match the filter. Reorder
 *  events pass through unfiltered — they're pure positional metadata
 *  with no field values to match on.
 *
 *  Section-title match short-circuits: if the filter matches the
 *  section's display label, every delta in the section stays visible
 *  (operators searching for the section by name want the whole
 *  section). */
function narrowDiff(diff: ConfigDiff, filter: FilterMatcher): ConfigDiff {
  const out = { ...diff } as ConfigDiff;
  for (const { key, label } of SECTION_LABELS) {
    const s = diff[key];
    if (!sectionHasChanges(s)) continue;
    if (filter.match(label)) continue; // title match → keep everything
    const narrowedModified = s.modified.filter((row) => {
      const hay = row.changes
        .map(
          (c) =>
            `${c.field} ${formatValueForHaystack(c.before)} ${formatValueForHaystack(c.after)}`,
        )
        .join(" ");
      return filter.match(`${row.label} ${hay}`);
    });
    (out[key] as SectionDiff) = {
      added: s.added.filter((r) => filter.match(rowHaystack(r))),
      removed: s.removed.filter((r) => filter.match(rowHaystack(r))),
      modified: narrowedModified,
      // Reordered stays as-is — there's nothing meaningful to match on.
      reordered: s.reordered,
      unchanged_count: s.unchanged_count,
    };
  }
  return out;
}

/** Flattens a diff-value to a plain string for filter matching. Mirrors
 *  the surface shown in the FieldChanges table; ``***redacted***``
 *  becomes the literal word ``redacted`` so operators can surface
 *  redaction-only diffs by typing "redacted". */
function formatValueForHaystack(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (v === "***redacted***") return "redacted";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  try {
    return JSON.stringify(v);
  } catch {
    return "";
  }
}


/** Summary strip — one chip per section with colored delta counts.
 *  Sections with zero changes are hidden (keeps it scannable when only
 *  a handful of sections drifted). Two orientations: the default
 *  horizontal flex-wrap strip at the top of the page, and a vertical
 *  stack for the sticky sidebar on wide viewports. */
function SummaryStrip({
  diff,
  orientation = "horizontal",
  activeId,
}: {
  diff: ConfigDiff;
  orientation?: "horizontal" | "vertical";
  activeId?: string | null;
}) {
  const entries = SECTION_LABELS.filter(({ key }) =>
    sectionHasChanges(diff[key]),
  );
  if (orientation === "vertical") {
    return (
      <nav
        aria-label="Changed sections"
        className="flex flex-col gap-0.5 rounded border border-border bg-muted/30 p-2 text-xs"
      >
        {entries.map(({ key, label, group }) => {
          const s = diff[key];
          const gc = groupClasses(group);
          const id = `diff-${String(key)}`;
          const active = activeId === id;
          return (
            <a
              key={key}
              href={`#${id}`}
              className={cn(
                "scroll-anchor flex items-center gap-1.5 rounded border-l-2 border-transparent px-2 py-1 hover:bg-muted",
                active && "border-accent bg-muted font-medium",
              )}
            >
              <span className={cn("flex-1 truncate", gc.title)}>{label}</span>
              {s.added.length > 0 && (
                <span
                  className="font-mono text-ok"
                  aria-label={`${s.added.length} added`}
                >
                  +{s.added.length}
                </span>
              )}
              {s.removed.length > 0 && (
                <span
                  className="font-mono text-danger"
                  aria-label={`${s.removed.length} removed`}
                >
                  −{s.removed.length}
                </span>
              )}
              {s.modified.length > 0 && (
                <span
                  className="font-mono text-warn"
                  aria-label={`${s.modified.length} modified`}
                >
                  ~{s.modified.length}
                </span>
              )}
              {s.reordered.length > 0 && (
                <span
                  className="font-mono text-info"
                  aria-label={`${s.reordered.length} reordered`}
                >
                  ↕{s.reordered.length}
                </span>
              )}
            </a>
          );
        })}
      </nav>
    );
  }
  return (
    <div className="flex flex-wrap gap-2 rounded border border-border bg-muted/30 p-2 text-xs">
      {entries.map(({ key, label, group }) => {
        const s = diff[key];
        const gc = groupClasses(group);
        return (
          <a
            key={key}
            href={`#diff-${String(key)}`}
            className={cn(
              "scroll-anchor inline-flex items-center gap-1.5 rounded border bg-bg px-2 py-1 hover:bg-muted",
              gc.chipBorder,
            )}
          >
            <span className={cn("font-medium", gc.title)}>{label}</span>
            {s.added.length > 0 && (
              <span className="font-mono text-ok">+{s.added.length}</span>
            )}
            {s.removed.length > 0 && (
              <span className="font-mono text-danger">−{s.removed.length}</span>
            )}
            {s.modified.length > 0 && (
              <span className="font-mono text-warn">~{s.modified.length}</span>
            )}
            {s.reordered.length > 0 && (
              <span className="font-mono text-info">↕{s.reordered.length}</span>
            )}
          </a>
        );
      })}
    </div>
  );
}

/** Two-up wrapper for the diff page. Mirrors ``ViewerLayout`` —
 *  sticky sidebar with filter + expand/collapse + summary strip above
 *  1700px, stacked layout below. The sidebar is 16rem here (vs the
 *  viewer's 15rem) because the diff's vertical summary strip chips
 *  carry colored delta counts (e.g. ``+3 ~5 −2``) on top of the
 *  section title — the extra rem keeps those from wrapping. Breakpoint
 *  crossover math: viewport − 16rem sidebar − 1.5rem gap − 2rem
 *  padding = narrow-mode content (1368px) at ~1716px ≈ 1700px. */
function DiffLayout({
  diff,
  filterQuery,
  setFilterQuery,
  sectionCounter,
  emptyBanner,
  children,
}: {
  diff: ConfigDiff;
  filterQuery: string;
  setFilterQuery: (next: string) => void;
  sectionCounter?: { visible: number; total: number };
  emptyBanner: ReactNode;
  children: ReactNode;
}) {
  const isWide = useMediaQuery("(min-width: 1700px)");
  // Pass ``filterQuery`` (not a count proxy) as the rebuild key so
  // two filters leaving the same number of diff sections visible
  // still refresh the observed element set.
  const activeId = useActiveSection(isWide ? "diff-" : null, filterQuery);

  if (isWide) {
    return (
      <div className="h-full overflow-auto p-4">
        <div className="mx-auto grid max-w-[1920px] grid-cols-[16rem_1fr] gap-6">
          <aside className="sticky top-0 max-h-screen self-start overflow-y-auto pb-4">
            <div className="flex flex-col gap-2 pb-3">
              <FilterBar
                value={filterQuery}
                onChange={setFilterQuery}
                sectionCounter={sectionCounter}
                placeholder="Filter (f)"
              />
              <ExpandCollapseAll orientation="vertical" />
            </div>
            <SummaryStrip diff={diff} orientation="vertical" activeId={activeId} />
          </aside>
          <div className="min-w-0">
            <FilterHiddenAnchorBanner onClear={() => setFilterQuery("")} />
            {emptyBanner}
            {children}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto p-4">
      <div className="mx-auto max-w-[1400px]">
        <div className="mb-2 flex items-start justify-between gap-3">
          <FilterBar
            value={filterQuery}
            onChange={setFilterQuery}
            sectionCounter={sectionCounter}
          />
          <ExpandCollapseAll />
        </div>
        <FilterHiddenAnchorBanner onClear={() => setFilterQuery("")} />
        {emptyBanner ?? <SummaryStrip diff={diff} />}
        {children}
      </div>
    </div>
  );
}

function DiffSectionCard({
  id,
  sectionKey,
  label,
  group,
  section,
}: {
  id: string;
  sectionKey: string;
  label: string;
  group: SectionGroup;
  section: SectionDiff;
}) {
  // Delta counts render as a muted subtitle at the top of the card
  // body instead of badge chips in the clickable header. That keeps
  // the section silhouette (`[▾] title [count]`) identical to every
  // structured-view Card.
  const summaryParts: string[] = [];
  if (section.added.length) summaryParts.push(`${section.added.length} added`);
  if (section.removed.length)
    summaryParts.push(`${section.removed.length} removed`);
  if (section.modified.length)
    summaryParts.push(`${section.modified.length} modified`);
  if (section.reordered.length)
    summaryParts.push(`${section.reordered.length} reordered`);
  return (
    <Card id={id} title={label} group={group}>
      <div className="space-y-3 text-sm">
        {summaryParts.length > 0 && (
          <div className="text-xs text-muted-fg">
            {summaryParts.join(" · ")}
          </div>
        )}
        {section.added.length > 0 && (
          <DiffGroup
            title="Added"
            tone="success"
            sectionKey={sectionKey}
            side="new"
            items={section.added.map((it, i) => ({
              id: String(i),
              label: labelForItem(it),
              item: it,
            }))}
          />
        )}
        {section.removed.length > 0 && (
          <DiffGroup
            title="Removed"
            tone="danger"
            sectionKey={sectionKey}
            side="old"
            items={section.removed.map((it, i) => ({
              id: String(i),
              label: labelForItem(it),
              item: it,
            }))}
          />
        )}
        {section.modified.length > 0 && (
          <ModifiedGroup rows={section.modified} sectionKey={sectionKey} />
        )}
        {section.reordered.length > 0 && (
          <ReorderedGroup rows={section.reordered} />
        )}
      </div>
    </Card>
  );
}

function labelForItem(item: Record<string, unknown>): string {
  // Best-effort label — prefer human-friendly fields over keys.
  for (const k of [
    "name",
    "descr",
    "description",
    "hostname",
    "tunable",
    "interface",
    "tag",
    "refid",
  ]) {
    const v = item[k];
    if (typeof v === "string" && v.trim()) return v;
  }
  const key = item["key"];
  if (typeof key === "string") return key;
  return "(entry)";
}

function DiffGroup({
  title,
  tone,
  sectionKey,
  side,
  items,
}: {
  title: string;
  tone: "success" | "danger";
  sectionKey: string;
  side: XrefSide;
  items: { id: string; label: string; item: Record<string, unknown> }[];
}) {
  return (
    <div>
      <div className="mb-1">
        <Badge tone={tone}>{title}</Badge>
      </div>
      <ul className="space-y-1">
        {items.map((it) => (
          <li
            key={it.id}
            className="rounded border border-border/70 bg-muted/20 p-2"
          >
            <div className="font-medium">{it.label}</div>
            <ItemJson item={it.item} sectionKey={sectionKey} side={side} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function ModifiedGroup({
  rows,
  sectionKey,
}: {
  rows: ItemDiff[];
  sectionKey: string;
}) {
  return (
    <div>
      <div className="mb-1">
        <Badge tone="warn">Modified</Badge>
      </div>
      <ul className="space-y-2">
        {rows.map((r) => (
          <li
            key={r.key}
            className="rounded border border-border/70 bg-muted/20 p-2"
          >
            <div className="mb-1 font-medium">{r.label}</div>
            <FieldChanges changes={r.changes} sectionKey={sectionKey} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function ReorderedGroup({ rows }: { rows: ReorderEvent[] }) {
  return (
    <div>
      <div className="mb-1">
        <Badge tone="muted">Reordered</Badge>
      </div>
      <p className="mb-1 text-xs text-muted-fg">
        Order matters for firewall / port-forward rules — pfSense evaluates
        top-to-bottom.
      </p>
      <ul className="space-y-1">
        {rows.map((r) => (
          <li key={r.key} className="rounded border border-border/70 bg-muted/20 p-1.5 font-mono text-xs">
            <span className="text-muted-fg">
              #{r.old_index + 1} → #{r.new_index + 1}
            </span>
            &nbsp;&nbsp;
            <span>{r.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function FieldChanges({
  changes,
  sectionKey,
}: {
  changes: FieldChange[];
  sectionKey: string;
}) {
  // v0.41.8: switched from auto-sized <table> to a fixed CSS grid
  // template so every modified-item card across every section
  // resolves to identical Field/Before/After column starts. With
  // the old <table>, each card's columns were sized by its own
  // content, so wide IP values pushed Before/After left on one
  // card and short values kept them right on the next — visually
  // impossible to scan down the diff. ``minmax(0, 1fr)`` disables
  // the default ``min-width: auto`` so long mono tokens wrap inside
  // their cell rather than inflating the track.
  //
  // v0.41.9: explicit table ARIA roles restore screen-reader table
  // navigation (JAWS / VoiceOver "next cell in column" etc.) that
  // was lost when the <table> markup became a <div> grid.
  //
  // v0.41.13: long mono values (``JSON.stringify``-d package entries
  // like ``{"name":"…","internal_name":"…",…}`` have no natural
  // break characters that CSS's default ``word-break: normal``
  // will break at, so the text overflowed its cell and bled into
  // the neighbouring column. ``min-w-0`` defeats the grid child's
  // default ``min-width: auto`` so the 1fr track actually shrinks
  // to 1fr instead of growing to its content.
  //
  // v0.41.17: switched from ``break-all`` (``word-break: break-all``,
  // which splits prose mid-word) to ``overflow-wrap: anywhere``.
  // Same "break when nothing else saves us" safety for unbreakable
  // mono tokens, but prose values (``description: (system): [pfSense-pkg-WireGuard]
  // Enabled all WireGuard gateways.``) now prefer space-based
  // breaks and stay readable.
  const cellBase = "font-mono min-w-0 [overflow-wrap:anywhere]";
  return (
    <div role="table" className="text-xs">
      <div
        role="row"
        className="grid grid-cols-[10rem_minmax(0,1fr)_minmax(0,1fr)] gap-x-4 py-0.5 uppercase text-muted-fg"
      >
        <div role="columnheader">Field</div>
        <div role="columnheader">Before</div>
        <div role="columnheader">After</div>
      </div>
      {changes.map((c) => {
        // v0.41.20: when both sides are arrays (e.g. DHCP
        // ``static_mappings``: 30+ devices each with
        // ``{mac, ipaddr, descr, …}``) the BEFORE and AFTER cells
        // used to render their lists independently — entries with
        // different field counts drifted out of row alignment so
        // device[0] BEFORE didn't sit next to device[0] AFTER, and
        // the gap grew with every subsequent index. Detect the
        // double-array case and render it as paired rows: index
        // ``i`` of BEFORE and AFTER live in the same outer grid
        // row (CSS Grid sizes the row to the taller cell) with a
        // ``divide-y`` line between indices.
        if (Array.isArray(c.before) && Array.isArray(c.after)) {
          return (
            <div
              key={c.field}
              role="row"
              className="grid grid-cols-[10rem_minmax(0,1fr)_minmax(0,1fr)] gap-x-4 border-t border-border/30 py-0.5"
            >
              <div role="cell" className={cellBase}>
                {c.field}
              </div>
              <PairedArrayCell
                before={c.before}
                after={c.after}
                sectionKey={sectionKey}
                field={c.field}
                cellBase={cellBase}
              />
            </div>
          );
        }
        return (
          <div
            key={c.field}
            role="row"
            className="grid grid-cols-[10rem_minmax(0,1fr)_minmax(0,1fr)] gap-x-4 border-t border-border/30 py-0.5"
          >
            <div role="cell" className={cellBase}>
              {c.field}
            </div>
            <div role="cell" className={`${cellBase} text-danger`}>
              <ValueChip
                sectionKey={sectionKey}
                field={c.field}
                value={c.before}
                side="old"
              />
            </div>
            <div role="cell" className={`${cellBase} text-ok`}>
              <ValueChip
                sectionKey={sectionKey}
                field={c.field}
                value={c.after}
                side="new"
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// v0.41.21 / v0.41.22: arrays come from the backend as whole
// BEFORE/AFTER blobs even when only 1-2 entries differ (e.g. DHCP
// ``static_mappings`` has 121 devices, edit one MAC, the field
// reports a 121-entry array on each side). Index-pairing breaks
// the moment an entry is added or removed mid-list — the
// reordered tail makes every subsequent index look "modified"
// even though all entries are unchanged. v0.41.22 pairs by
// natural key (``host`` for DNS host_overrides, ``mac`` for DHCP
// static mappings, ``tracker`` / ``refid`` / ``name`` for rule
// lists) when one is detectable; identical pairs collapse to a
// "N identical entries" placeholder and only true changes (added,
// removed, modified) render in full color. Falls back to
// index-pairing when no key is detectable (string arrays,
// shape-irregular arrays).
// Field candidates checked first as single-field keys, then in
// pairs for compound-key detection. Order matters — narrower /
// rarer identifiers go first so e.g. ``tracker`` wins over the
// less-distinctive ``name``. ``domain`` and ``interface`` round
// out the list as common second-half partners (``host`` +
// ``domain`` for DNS, ``name`` + ``interface`` for some rule
// shapes, etc.).
const KEY_CANDIDATES = [
  "tracker",
  "refid",
  "id",
  "uuid",
  "name",
  "host",
  "mac",
  "hostname",
  "key",
  "domain",
  "type",
  "interface",
];

function entryKey(e: unknown, fields: string[]): string | null {
  if (!e || typeof e !== "object" || Array.isArray(e)) return null;
  const obj = e as Record<string, unknown>;
  const parts: string[] = [];
  for (const f of fields) {
    const v = obj[f];
    if (v === undefined || v === null || v === "") return null;
    parts.push(String(v));
  }
  // ``\x00`` separator avoids collisions like ``"a"+"b"`` colliding
  // with ``"ab"+""``.
  return parts.join("\x00");
}

// v0.41.24: tolerate null/empty key values. ``static_mappings``
// often has a single entry with an empty ``mac`` (DHCP-pool-only
// row, no static reservation) — strict isUniqueKey rejected
// ``mac`` for the whole 121-entry array because of that one
// outlier, falling back to index pairing for everything. Now we
// skip null-key entries during uniqueness checking and let the
// caller fall those entries through to deepEq matching at the
// tail. Require at least one non-null match so we don't pick a
// candidate where every entry is null.
function isUniqueKey(entries: unknown[], fields: string[]): boolean {
  if (entries.length === 0) return false;
  const seen = new Set<string>();
  for (const e of entries) {
    const k = entryKey(e, fields);
    if (k === null) continue;
    if (seen.has(k)) return false;
    seen.add(k);
  }
  return seen.size > 0;
}

// v0.41.23: extended ``detectKey`` to try COMPOUND keys when no
// single field is unique. DNS ``host_overrides`` for example may
// have multiple entries with ``host: "pikvm"`` differing only by
// ``domain`` — single ``host`` is rejected, but ``host`` +
// ``domain`` is unique. Without this, the cell falls back to
// index-pairing and reorders look like cascading "modifications".
function detectKey(entries: unknown[]): string[] | null {
  if (entries.length === 0) return null;
  for (const cand of KEY_CANDIDATES) {
    if (isUniqueKey(entries, [cand])) return [cand];
  }
  for (let i = 0; i < KEY_CANDIDATES.length; i++) {
    for (let j = i + 1; j < KEY_CANDIDATES.length; j++) {
      const combo = [KEY_CANDIDATES[i], KEY_CANDIDATES[j]];
      if (isUniqueKey(entries, combo)) return combo;
    }
  }
  return null;
}

// Pick a key that's unique on BOTH sides (so we can pair). Try
// detection on each side and verify it works on the other.
function detectSharedKey(
  before: unknown[],
  after: unknown[],
): string[] | null {
  const k1 = detectKey(before);
  if (k1 && isUniqueKey(after, k1)) return k1;
  const k2 = detectKey(after);
  if (k2 && isUniqueKey(before, k2)) return k2;
  return null;
}

type PairItem = {
  kind: "pair";
  before: unknown | null;
  after: unknown | null;
  label?: string;
};
type SkipItem = { kind: "skip"; count: number };

function PairedArrayCell({
  before,
  after,
  sectionKey,
  field,
  cellBase,
}: {
  before: unknown[];
  after: unknown[];
  sectionKey: string;
  field: string;
  cellBase: string;
}) {
  const [showAll, setShowAll] = useState(false);

  const allPairs = useMemo<PairItem[]>(() => {
    const keyFields = detectSharedKey(before, after);
    if (keyFields) {
      // Split each side into keyed (has all key fields) and
      // unkeyed (missing or empty in at least one key field).
      // Keyed entries pair by key. Unkeyed entries pair by
      // greedy deepEq scan as a fallback so e.g. a ``mac=""``
      // DHCP-range-only row that exists identically on both
      // sides still collapses to identical instead of looking
      // like one removed + one added.
      const beforeKeyed: { k: string; v: unknown }[] = [];
      const beforeUnkeyed: unknown[] = [];
      for (const e of before) {
        const k = entryKey(e, keyFields);
        if (k !== null) beforeKeyed.push({ k, v: e });
        else beforeUnkeyed.push(e);
      }
      const afterKeyed: { k: string; v: unknown }[] = [];
      const afterUnkeyed: unknown[] = [];
      for (const e of after) {
        const k = entryKey(e, keyFields);
        if (k !== null) afterKeyed.push({ k, v: e });
        else afterUnkeyed.push(e);
      }
      const afterMap = new Map<string, unknown>();
      for (const { k, v } of afterKeyed) afterMap.set(k, v);

      const out: PairItem[] = [];
      const seen = new Set<string>();
      for (const { k, v } of beforeKeyed) {
        seen.add(k);
        out.push({
          kind: "pair",
          before: v,
          after: afterMap.get(k) ?? null,
          label: k,
        });
      }
      for (const { k, v } of afterKeyed) {
        if (!seen.has(k)) {
          seen.add(k);
          out.push({ kind: "pair", before: null, after: v, label: k });
        }
      }
      // Greedy deepEq matching for the unkeyed remainder.
      const afterTaken = new Array<boolean>(afterUnkeyed.length).fill(false);
      for (const b of beforeUnkeyed) {
        let matched = -1;
        for (let i = 0; i < afterUnkeyed.length; i++) {
          if (afterTaken[i]) continue;
          if (deepEq(b, afterUnkeyed[i])) {
            matched = i;
            break;
          }
        }
        if (matched >= 0) {
          afterTaken[matched] = true;
          out.push({ kind: "pair", before: b, after: afterUnkeyed[matched] });
        } else {
          out.push({ kind: "pair", before: b, after: null });
        }
      }
      for (let i = 0; i < afterUnkeyed.length; i++) {
        if (!afterTaken[i]) {
          out.push({ kind: "pair", before: null, after: afterUnkeyed[i] });
        }
      }
      return out;
    }
    // No detectable key — fall back to index-pairing.
    const n = Math.max(before.length, after.length);
    return Array.from({ length: n }).map<PairItem>((_, i) => ({
      kind: "pair",
      before: i < before.length ? before[i] : null,
      after: i < after.length ? after[i] : null,
    }));
  }, [before, after]);

  const collapsedItems = useMemo<(PairItem | SkipItem)[]>(() => {
    const out: (PairItem | SkipItem)[] = [];
    let runCount = 0;
    for (const p of allPairs) {
      const same =
        p.before !== null && p.after !== null && deepEq(p.before, p.after);
      if (same) {
        runCount += 1;
      } else {
        if (runCount > 0) {
          out.push({ kind: "skip", count: runCount });
          runCount = 0;
        }
        out.push(p);
      }
    }
    if (runCount > 0) out.push({ kind: "skip", count: runCount });
    return out;
  }, [allPairs]);

  const collapsedCount = useMemo(
    () =>
      collapsedItems
        .filter((it): it is SkipItem => it.kind === "skip")
        .reduce((s, it) => s + it.count, 0),
    [collapsedItems],
  );

  const items: (PairItem | SkipItem)[] = showAll ? allPairs : collapsedItems;

  return (
    <div className="col-span-2">
      <div className="grid grid-cols-2 gap-x-4 divide-y divide-border/30">
        {items.map((item, idx) =>
          item.kind === "pair" ? (
            <Fragment key={`p${idx}`}>
              <div className={`${cellBase} py-1 text-danger`}>
                {item.before !== null ? (
                  <ValueChip
                    sectionKey={sectionKey}
                    field={field}
                    value={item.before}
                    side="old"
                  />
                ) : (
                  <span className="text-muted-fg">—</span>
                )}
              </div>
              <div className={`${cellBase} py-1 text-ok`}>
                {item.after !== null ? (
                  <ValueChip
                    sectionKey={sectionKey}
                    field={field}
                    value={item.after}
                    side="new"
                  />
                ) : (
                  <span className="text-muted-fg">—</span>
                )}
              </div>
            </Fragment>
          ) : (
            <div
              key={`s${idx}`}
              className="col-span-2 py-1 text-xs italic text-muted-fg"
            >
              {item.count === 1
                ? "1 identical entry"
                : `${item.count} identical entries`}
            </div>
          ),
        )}
      </div>
      {collapsedCount > 0 && (
        <button
          type="button"
          onClick={() => setShowAll((s) => !s)}
          className="mt-1 text-xs text-accent hover:underline"
        >
          {showAll
            ? "Collapse identical entries"
            : `Show all ${allPairs.length} entries`}
        </button>
      )}
    </div>
  );
}

function deepEq(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a === null || b === null) return a === b;
  if (typeof a !== typeof b) return false;
  if (typeof a !== "object") return false;
  const aArr = Array.isArray(a);
  const bArr = Array.isArray(b);
  if (aArr !== bArr) return false;
  if (aArr) {
    const aa = a as unknown[];
    const ba = b as unknown[];
    if (aa.length !== ba.length) return false;
    for (let i = 0; i < aa.length; i++) {
      if (!deepEq(aa[i], ba[i])) return false;
    }
    return true;
  }
  const ao = a as Record<string, unknown>;
  const bo = b as Record<string, unknown>;
  const ka = Object.keys(ao);
  const kb = Object.keys(bo);
  if (ka.length !== kb.length) return false;
  for (const k of ka) {
    if (!Object.prototype.hasOwnProperty.call(bo, k)) return false;
    if (!deepEq(ao[k], bo[k])) return false;
  }
  return true;
}

function formatValue(v: unknown): ReactNode {
  if (v === null || v === undefined) return <span className="text-muted-fg">—</span>;
  if (v === "***redacted***")
    return (
      <span className="inline-flex items-center gap-1 rounded border border-[hsl(var(--group-vpn))]/30 bg-[hsl(var(--group-vpn))]/10 px-1.5 py-0.5 font-mono text-[11px] text-[hsl(var(--group-vpn))]">
        <Lock aria-hidden="true" className="h-3 w-3" /> redacted
      </span>
    );
  if (Array.isArray(v)) return formatArray(v);
  if (typeof v === "object") return formatObject(v as Record<string, unknown>);
  // v0.41.19: pfSense package configs embed XML *strings* that the
  // parser doesn't decode further (e.g. ``installedpackages.unknown``
  // entries hold a raw ``<tab><name>…</name><tabgroup>…</tabgroup>…</tab>``
  // blob). Detect XML-shaped strings and pretty-print with one tag
  // per line + indentation so the nested structure is visible at a
  // glance instead of one wrapping run-on of mono characters.
  if (typeof v === "string" && isXmlLike(v)) {
    return (
      <pre className="whitespace-pre-wrap font-mono">{prettyXml(v)}</pre>
    );
  }
  return String(v);
}

function isXmlLike(s: string): boolean {
  // Heuristic: starts with ``<`` followed by a name char (not ``?`` so
  // we skip ``<?xml ...?>`` headers, not ``!`` so we skip comments and
  // doctype). Must contain at least one closing tag so a stray
  // ``<value/>`` alone doesn't trip it. A trimmed-leading-whitespace
  // form so values like ``"  <tab>…"`` still match.
  const trimmed = s.trimStart();
  return (
    trimmed.length > 1 &&
    trimmed[0] === "<" &&
    trimmed[1] !== "?" &&
    trimmed[1] !== "!" &&
    /<\/[\w:.-]+>/.test(s)
  );
}

function prettyXml(s: string): string {
  // Tokenize at every ``><`` boundary so each tag (and the text
  // between tags) lands on its own line. Then indent based on a
  // running ``depth`` counter — increment on opening tags, decrement
  // on closing tags, leave self-closing (``<foo/>``) alone. We do
  // *not* try to be a real XML parser; pfSense's embedded XML is
  // small and well-formed enough that a token-counter is sufficient
  // and 100% safe (no eval, no DOMParser, no allocation surprises).
  const tokens = s
    .replace(/>\s+</g, "><")
    .replace(/></g, ">\n<")
    .split("\n");
  let depth = 0;
  const out: string[] = [];
  for (const raw of tokens) {
    const line = raw.trim();
    if (!line) continue;
    const isClose = /^<\/[\w:.-]+\s*>$/.test(line);
    const isSelfClose = /\/>\s*$/.test(line);
    const isOpen = /^<[\w:.-][^>]*[^/]>$/.test(line) && !isClose;
    if (isClose) depth = Math.max(0, depth - 1);
    out.push("  ".repeat(depth) + line);
    if (isOpen && !isSelfClose) depth += 1;
  }
  return out.join("\n");
}

// v0.41.15: previously ``formatValue`` called ``JSON.stringify`` for
// objects + arrays, which dumped raw ``{"name":"…","descr":"…",…}``
// strings into the diff's Before/After cells — the opposite of the
// "structured view" look. Now we render the same shape the
// structured view does: objects become a 2-col label/value grid
// (Dl-shape), arrays become a vertical list, and each nested value
// recurses back into ``formatValue`` so deeply-nested content still
// reads as structured data.
function formatObject(o: Record<string, unknown>): ReactNode {
  const entries = Object.entries(o).filter(
    ([, val]) =>
      val !== null && val !== undefined && val !== "" && val !== false,
  );
  if (entries.length === 0) return <span className="text-muted-fg">—</span>;
  return (
    <div className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-0.5">
      {entries.map(([k, val]) => (
        <Fragment key={k}>
          <span className="text-muted-fg">{k}</span>
          <span className="min-w-0 [overflow-wrap:anywhere]">{formatValue(val)}</span>
        </Fragment>
      ))}
    </div>
  );
}

function formatArray(a: unknown[]): ReactNode {
  if (a.length === 0) return <span className="text-muted-fg">—</span>;
  // v0.41.19: switched from ``space-y-0.5`` to ``divide-y`` because
  // an array of objects (e.g. DHCP ``static_mappings`` with 30+
  // entries, each ``{mac, ipaddr, descr, …}``) ran together with no
  // visual delimiter — operators saw one continuous stream of
  // ``mac ea:da:… ipaddr 10.10.76.3 descr Serapis mac 48:21:… …``
  // and couldn't tell where one entry ended and the next started.
  // A thin divider per item makes each array element a distinct
  // block; ``py-1`` gives the divider room to breathe.
  return (
    <ul className="divide-y divide-border/30">
      {a.map((v, i) => (
        <li key={i} className="min-w-0 py-1 [overflow-wrap:anywhere]">
          {formatValue(v)}
        </li>
      ))}
    </ul>
  );
}

function ItemJson({
  item,
  sectionKey,
  side,
}: {
  item: Record<string, unknown>;
  sectionKey: string;
  side: XrefSide;
}) {
  // v0.41.14: was a bespoke <table> with its own typography. Swapped
  // for the shared ``Dl`` primitive so added/removed item fields
  // render with identical label/value spacing to the structured view
  // (Interfaces, OpenVPN, …). The side-tone color stays on the
  // value only — the structured view's Dl uses ``text-muted-fg`` on
  // labels, which we preserve so the side's red/green doesn't
  // shout across the whole row.
  const entries = Object.entries(item)
    .filter(([k, v]) => {
      if (k === "key" || k === "label") return false;
      if (v === null || v === "" || v === false) return false;
      if (Array.isArray(v) && v.length === 0) return false;
      return true;
    })
    .slice(0, 12);
  if (entries.length === 0) return null;
  const rows: DlRow[] = entries.map(([k, v]) => [
    k,
    <span className={side === "new" ? "text-ok" : "text-danger"}>
      <ValueChip sectionKey={sectionKey} field={k} value={v} side={side} />
    </span>,
  ]);
  return <Dl items={rows} />;
}
