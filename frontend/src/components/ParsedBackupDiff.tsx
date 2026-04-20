import { useMemo } from "react";
import { Lock } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Alert } from "@/components/ui/Alert";
import { useParsedDiffPair } from "@/api/queries";
import { cn } from "@/lib/cn";
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
  lbl("unrecognized_sections", "Other sections"),
];

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
  const { data, error, isLoading } = useParsedDiffPair(a, b);

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
  if (!data) return null;

  const totalChanges = SECTION_LABELS.reduce(
    (n, { key }) => n + changeCount(data[key]),
    0,
  );

  return (
    <div className="h-full overflow-auto p-4">
      <div className="mx-auto max-w-[1400px]">
        {totalChanges === 0 ? (
          <Alert tone="ok" title="No changes">
            No semantic changes detected across any tracked section.
          </Alert>
        ) : (
          <SummaryStrip diff={data} />
        )}
        <div className="mt-4 space-y-3">
          {SECTION_LABELS.map(({ key, label, group }) => {
            const s = data[key];
            if (!sectionHasChanges(s)) return null;
            return (
              <DiffSectionCard
                key={key}
                id={`diff-${String(key)}`}
                label={label}
                group={group}
                section={s}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

/** The top summary strip — one chip per section with colored delta
 *  counts. Sections with zero changes are hidden (keeps the strip
 *  scannable when only a handful of sections drifted). */
function SummaryStrip({ diff }: { diff: ConfigDiff }) {
  return (
    <div className="flex flex-wrap gap-2 rounded border border-border bg-muted/30 p-2 text-xs">
      {SECTION_LABELS.map(({ key, label, group }) => {
        const s = diff[key];
        if (!sectionHasChanges(s)) return null;
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

function DiffSectionCard({
  id,
  label,
  group,
  section,
}: {
  id: string;
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
            items={section.removed.map((it, i) => ({
              id: String(i),
              label: labelForItem(it),
              item: it,
            }))}
          />
        )}
        {section.modified.length > 0 && (
          <ModifiedGroup rows={section.modified} />
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
  items,
}: {
  title: string;
  tone: "success" | "danger";
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
            <ItemJson item={it.item} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function ModifiedGroup({ rows }: { rows: ItemDiff[] }) {
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
            <FieldChanges changes={r.changes} />
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

function FieldChanges({ changes }: { changes: FieldChange[] }) {
  return (
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
              {formatValue(c.before)}
            </td>
            <td className="py-0.5 font-mono text-ok">
              {formatValue(c.after)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
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

function ItemJson({ item }: { item: Record<string, unknown> }) {
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
    <table className="w-full text-xs">
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k} className="border-t border-border/30">
            <td className="py-0.5 pr-2 font-mono text-muted-fg">{k}</td>
            <td className="py-0.5 font-mono">{formatValue(v)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
