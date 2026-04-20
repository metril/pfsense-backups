import { useCallback, useMemo, type ReactNode } from "react";
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
import { DeepLinkBridge } from "@/components/xref/DeepLinkBridge";
import { useParsedBackup, useParsedDiffPair } from "@/api/queries";
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
  const { data: oldCfg } = useParsedBackup(a);
  const { data: newCfg } = useParsedBackup(b);

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
        <DeepLinkBridge includeHashchange />
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
  oldCfg: ReturnType<typeof useParsedBackup>["data"];
  newCfg: ReturnType<typeof useParsedBackup>["data"];
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
 *  1400px, stacked layout below. */
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
  const isWide = useMediaQuery("(min-width: 1400px)");
  // Version the observer on ``sectionCounter.visible`` so the
  // IntersectionObserver is rebuilt when the filter changes the
  // set of rendered diff section cards.
  const activeId = useActiveSection(
    isWide ? "diff-" : null,
    sectionCounter?.visible ?? 0,
  );

  if (isWide) {
    return (
      <div className="h-full overflow-auto p-4">
        <div className="mx-auto grid max-w-[1600px] grid-cols-[16rem_1fr] gap-6">
          <aside className="sticky top-0 max-h-screen self-start overflow-y-auto pb-4">
            <div className="flex flex-col gap-2 pb-3">
              <FilterBar
                value={filterQuery}
                onChange={setFilterQuery}
                sectionCounter={sectionCounter}
                placeholder="Filter (f)"
              />
              <ExpandCollapseAll />
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
        <div className="mb-2 flex items-center justify-between gap-3">
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
  // Memoized so Card doesn't see a fresh JSX element on every parent
  // render. Deps are just the four delta counts — stable across
  // unrelated state updates (tab switches, collapse toggles elsewhere).
  const headerExtra = useMemo(
    () => (
      <>
        {section.added.length > 0 && (
          <Badge tone="success">+{section.added.length}</Badge>
        )}
        {section.removed.length > 0 && (
          <Badge tone="danger">−{section.removed.length}</Badge>
        )}
        {section.modified.length > 0 && (
          <Badge tone="warn">~{section.modified.length}</Badge>
        )}
        {section.reordered.length > 0 && (
          <Badge tone="muted">↕{section.reordered.length}</Badge>
        )}
      </>
    ),
    [
      section.added.length,
      section.removed.length,
      section.modified.length,
      section.reordered.length,
    ],
  );
  return (
    <Card
      id={id}
      title={label}
      group={group}
      headerExtra={headerExtra}
    >
      <div className="space-y-3 text-sm">
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
            className={cn(
              "rounded border p-2",
              tone === "success"
                ? "border-ok/30 bg-ok/5"
                : "border-danger/30 bg-danger/5",
            )}
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
            className="rounded border border-warn/30 bg-warn/5 p-2"
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
          <li key={r.key} className="rounded border border-info/30 bg-info/5 p-1.5 font-mono text-xs">
            <span className="text-info">
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
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-muted-fg">
            <th className="py-0.5 text-left font-normal">Field</th>
            <th className="py-0.5 text-left font-normal">Before</th>
            <th className="py-0.5 text-left font-normal">After</th>
          </tr>
        </thead>
        <tbody>
          {changes.map((c) => (
            <tr key={c.field} className="border-t border-border/30">
              <td className="py-0.5 pr-2 font-mono">{c.field}</td>
              <td className="py-0.5 pr-2 font-mono text-danger">
                <ValueChip
                  sectionKey={sectionKey}
                  field={c.field}
                  value={c.before}
                  side="old"
                />
              </td>
              <td className="py-0.5 font-mono text-ok">
                <ValueChip
                  sectionKey={sectionKey}
                  field={c.field}
                  value={c.after}
                  side="new"
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatValue(v: unknown): React.ReactNode {
  if (v === null || v === undefined) return <span className="text-muted-fg">—</span>;
  if (v === "***redacted***")
    return (
      <span className="inline-flex items-center gap-1 rounded border border-[hsl(var(--group-vpn))]/30 bg-[hsl(var(--group-vpn))]/10 px-1.5 py-0.5 font-mono text-[11px] text-[hsl(var(--group-vpn))]">
        <Lock aria-hidden="true" className="h-3 w-3" /> redacted
      </span>
    );
  if (Array.isArray(v)) return JSON.stringify(v);
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
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
  // Compact inline summary of the added/removed item. Show a small set
  // of the most informative fields; the full object is available via
  // the raw XML tab if the operator needs exhaustive detail.
  const entries = Object.entries(item)
    .filter(([k, v]) => {
      if (k === "key" || k === "label") return false;
      if (v === null || v === "" || v === false) return false;
      if (Array.isArray(v) && v.length === 0) return false;
      return true;
    })
    .slice(0, 12);
  if (entries.length === 0) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <tbody>
          {entries.map(([k, v]) => (
            <tr key={k} className="border-t border-border/30">
              <td className="py-0.5 pr-2 font-mono text-muted-fg">{k}</td>
              <td className="py-0.5 font-mono">
                <ValueChip
                  sectionKey={sectionKey}
                  field={k}
                  value={v}
                  side={side}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
