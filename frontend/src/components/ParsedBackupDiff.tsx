import { useState } from "react";
import { ChevronDown, ChevronRight, Lock } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { useParsedDiffPair } from "@/api/queries";
import type {
  ConfigDiff,
  FieldChange,
  ItemDiff,
  ReorderEvent,
  SectionDiff,
} from "@/api/parsedTypes";

/** Per-section labels shown in the summary strip. Keys match
 *  ConfigDiff property names one-to-one. */
const SECTION_LABELS: { key: keyof ConfigDiff; label: string }[] = [
  { key: "config_version", label: "Config schema" },
  { key: "system", label: "System" },
  { key: "revision", label: "Last revision" },
  { key: "interfaces", label: "Interfaces" },
  { key: "vlans", label: "VLANs" },
  { key: "bridges", label: "Bridges" },
  { key: "gifs", label: "GIF tunnels" },
  { key: "gres", label: "GRE tunnels" },
  { key: "ppps", label: "PPP interfaces" },
  { key: "qinqs", label: "QinQ" },
  { key: "wol", label: "Wake-on-LAN" },
  { key: "virtual_ips", label: "Virtual IPs / CARP" },
  { key: "hasync", label: "HA / CARP sync" },
  { key: "gateways", label: "Gateways" },
  { key: "gateway_groups", label: "Gateway groups" },
  { key: "static_routes", label: "Static routes" },
  { key: "firewall_rules", label: "Firewall rules" },
  { key: "nat_rules", label: "NAT rules" },
  { key: "aliases", label: "Aliases" },
  { key: "dhcp_servers", label: "DHCP servers" },
  { key: "dhcp_relays", label: "DHCP relay" },
  { key: "dns", label: "DNS" },
  { key: "ntpd", label: "NTP server" },
  { key: "snmpd", label: "SNMP" },
  { key: "syslog", label: "Remote syslog" },
  { key: "schedules", label: "Schedules" },
  { key: "shaper_queues", label: "Shaper queues" },
  { key: "dnshaper_pipes", label: "Limiter pipes" },
  { key: "lb_pools", label: "LB pools" },
  { key: "lb_virtual_servers", label: "LB virtual servers" },
  { key: "captive_portal_zones", label: "Captive portal" },
  { key: "users", label: "Users" },
  { key: "groups", label: "Groups" },
  { key: "authservers", label: "Auth servers" },
  { key: "sysctl", label: "Sysctl" },
  { key: "cron", label: "Cron" },
  { key: "unrecognized_sections", label: "Other sections" },
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
  return s.added.length + s.removed.length + s.modified.length + s.reordered.length;
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
      <div className="p-6 text-sm text-danger">
        Could not compute diff: {String(error)}
      </div>
    );
  if (!data) return null;

  const totalChanges = SECTION_LABELS.reduce(
    (n, { key }) => n + changeCount(data[key]),
    0,
  );

  return (
    <div className="h-full overflow-auto p-4">
      {totalChanges === 0 ? (
        <div className="rounded border border-border bg-ok/10 p-4 text-sm text-ok">
          No semantic changes detected across any tracked section.
        </div>
      ) : (
        <SummaryStrip diff={data} />
      )}
      <div className="mt-4 space-y-3">
        {SECTION_LABELS.map(({ key, label }) => {
          const s = data[key];
          if (!sectionHasChanges(s)) return null;
          return <SectionCard key={key} label={label} section={s} />;
        })}
      </div>
    </div>
  );
}

function SummaryStrip({ diff }: { diff: ConfigDiff }) {
  return (
    <div className="flex flex-wrap gap-2 rounded border border-border bg-muted/30 p-2 text-xs">
      {SECTION_LABELS.map(({ key, label }) => {
        const s = diff[key];
        if (!sectionHasChanges(s)) return null;
        const parts: string[] = [];
        if (s.added.length) parts.push(`+${s.added.length}`);
        if (s.removed.length) parts.push(`−${s.removed.length}`);
        if (s.modified.length) parts.push(`~${s.modified.length}`);
        if (s.reordered.length) parts.push(`↕${s.reordered.length}`);
        return (
          <a
            key={key}
            href={`#diff-${key}`}
            className="inline-flex items-center gap-1 rounded border border-border bg-bg px-2 py-0.5 hover:bg-muted"
          >
            <span>{label}</span>
            <span className="font-mono text-accent">{parts.join(" ")}</span>
          </a>
        );
      })}
    </div>
  );
}

function SectionCard({
  label,
  section,
}: {
  label: string;
  section: SectionDiff;
}) {
  const [open, setOpen] = useState(true);
  return (
    <section
      id={`diff-${label.toLowerCase().replace(/\s+/g, "-")}`}
      className="rounded border border-border bg-bg"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-medium hover:bg-muted/50"
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown className="h-4 w-4 text-muted-fg" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-fg" />
        )}
        <span>{label}</span>
        <div className="flex gap-1">
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
        </div>
      </button>
      {open && (
        <div className="space-y-3 border-t border-border p-3 text-sm">
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
      )}
    </section>
  );
}

function labelForItem(item: Record<string, unknown>): string {
  // Best-effort label — prefer human-friendly fields over keys.
  for (const k of ["name", "descr", "hostname", "tunable", "interface", "tag"]) {
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
      <div className="mb-1 text-xs uppercase text-muted-fg">
        <Badge tone={tone}>{title}</Badge>
      </div>
      <ul className="space-y-1">
        {items.map((it) => (
          <li
            key={it.id}
            className="rounded border border-border/50 bg-muted/20 p-2"
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
      <div className="mb-1 text-xs uppercase text-muted-fg">
        <Badge tone="warn">Modified</Badge>
      </div>
      <ul className="space-y-2">
        {rows.map((r) => (
          <li
            key={r.key}
            className="rounded border border-border/50 bg-muted/20 p-2"
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
      <div className="mb-1 text-xs uppercase text-muted-fg">
        <Badge tone="muted">Reordered</Badge>
      </div>
      <p className="mb-1 text-xs text-muted-fg">
        Order matters for firewall / port-forward rules — pfSense evaluates
        top-to-bottom.
      </p>
      <ul className="space-y-1">
        {rows.map((r) => (
          <li key={r.key} className="font-mono text-xs">
            #{r.old_index + 1} → #{r.new_index + 1} &nbsp; {r.label}
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
            <td className="py-0.5 pr-2 font-mono text-danger/80">
              {formatValue(c.before)}
            </td>
            <td className="py-0.5 font-mono text-ok/80">
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
      <span className="inline-flex items-center gap-1 text-muted-fg">
        <Lock className="h-3 w-3" /> redacted
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
