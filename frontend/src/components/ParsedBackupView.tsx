import { useState } from "react";
import { ChevronDown, ChevronRight, Lock } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { useParsedBackup } from "@/api/queries";
import type {
  Alias,
  AuthServer,
  CronJob,
  DhcpServer,
  DnsConfig,
  FirewallRule,
  Gateway,
  Group,
  Interface,
  NatRule,
  ParsedConfig,
  RawSection,
  StaticRoute,
  SysctlTunable,
  SystemInfo,
  User,
} from "@/api/parsedTypes";

/** Render a server-parsed pfSense config as collapsible sections.
 *
 * The value comes from `/api/backups/{id}/parsed`. Secrets (password
 * hashes, VPN PSKs, RADIUS shared secrets, etc.) are replaced with the
 * string `"***redacted***"` on the server so this component never has
 * the plaintext to leak. We render redacted values with a lock glyph
 * so operators see exactly which fields are hidden.
 */
export function ParsedBackupView({ backupId }: { backupId: number }) {
  const { data, error, isLoading } = useParsedBackup(backupId);

  if (isLoading)
    return <div className="p-6 text-sm text-muted-fg">Parsing config…</div>;
  if (error)
    return (
      <div className="p-6 text-sm text-danger">
        Could not parse config: {String(error)}
      </div>
    );
  if (!data) return null;

  return (
    <div className="h-full overflow-auto p-4">
      <TableOfContents cfg={data} />
      <div className="mt-4 space-y-3">
        {data.system && (
          <Section title="System" count={1}>
            <SystemPanel s={data.system} />
          </Section>
        )}
        {data.revision && (
          <Section title="Last revision" count={1}>
            <Dl
              items={[
                ["When", data.revision.time ?? "—"],
                ["By", data.revision.username ?? "—"],
                ["Description", data.revision.description ?? "—"],
              ]}
            />
          </Section>
        )}
        {data.interfaces.length > 0 && (
          <Section title="Interfaces" count={data.interfaces.length}>
            <InterfacesTable rows={data.interfaces} />
          </Section>
        )}
        {data.gateways.length > 0 && (
          <Section title="Gateways" count={data.gateways.length}>
            <GatewaysTable rows={data.gateways} />
          </Section>
        )}
        {data.static_routes.length > 0 && (
          <Section title="Static routes" count={data.static_routes.length}>
            <StaticRoutesTable rows={data.static_routes} />
          </Section>
        )}
        {data.firewall_rules.length > 0 && (
          <Section title="Firewall rules" count={data.firewall_rules.length}>
            <FirewallTable rows={data.firewall_rules} />
          </Section>
        )}
        {data.nat_rules.length > 0 && (
          <Section title="NAT rules" count={data.nat_rules.length}>
            <NatTable rows={data.nat_rules} />
          </Section>
        )}
        {data.aliases.length > 0 && (
          <Section title="Aliases" count={data.aliases.length}>
            <AliasesTable rows={data.aliases} />
          </Section>
        )}
        {data.dhcp_servers.length > 0 && (
          <Section title="DHCP servers" count={data.dhcp_servers.length}>
            <DhcpTable rows={data.dhcp_servers} />
          </Section>
        )}
        {data.dns && (
          <Section title="DNS" count={1}>
            <DnsPanel d={data.dns} />
          </Section>
        )}
        {data.users.length > 0 && (
          <Section title="Users" count={data.users.length}>
            <UsersTable rows={data.users} />
          </Section>
        )}
        {data.groups.length > 0 && (
          <Section title="Groups" count={data.groups.length}>
            <GroupsTable rows={data.groups} />
          </Section>
        )}
        {data.authservers.length > 0 && (
          <Section
            title="External auth servers"
            count={data.authservers.length}
          >
            <AuthServersTable rows={data.authservers} />
          </Section>
        )}
        {data.sysctl.length > 0 && (
          <Section title="Sysctl tunables" count={data.sysctl.length}>
            <SysctlTable rows={data.sysctl} />
          </Section>
        )}
        {data.cron.length > 0 && (
          <Section title="Cron jobs" count={data.cron.length}>
            <CronTable rows={data.cron} />
          </Section>
        )}
        {data.unrecognized_sections.length > 0 && (
          <Section
            title="Other sections (raw XML)"
            count={data.unrecognized_sections.length}
            muted
          >
            <UnrecognizedList rows={data.unrecognized_sections} />
          </Section>
        )}
      </div>
    </div>
  );
}

// ---------- primitives -----------------------------------------------------

function Section({
  title,
  count,
  muted,
  children,
}: {
  title: string;
  count: number;
  muted?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  return (
    <section
      id={sectionId(title)}
      className="rounded border border-border bg-bg"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-medium hover:bg-muted/50"
      >
        {open ? (
          <ChevronDown className="h-4 w-4 text-muted-fg" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-fg" />
        )}
        <span className={muted ? "text-muted-fg" : ""}>{title}</span>
        <Badge tone="muted">{count}</Badge>
      </button>
      {open && <div className="border-t border-border p-3">{children}</div>}
    </section>
  );
}

function TableOfContents({ cfg }: { cfg: ParsedConfig }) {
  const entries: [string, number][] = [];
  if (cfg.system) entries.push(["System", 1]);
  if (cfg.revision) entries.push(["Last revision", 1]);
  if (cfg.interfaces.length) entries.push(["Interfaces", cfg.interfaces.length]);
  if (cfg.gateways.length) entries.push(["Gateways", cfg.gateways.length]);
  if (cfg.static_routes.length)
    entries.push(["Static routes", cfg.static_routes.length]);
  if (cfg.firewall_rules.length)
    entries.push(["Firewall rules", cfg.firewall_rules.length]);
  if (cfg.nat_rules.length) entries.push(["NAT rules", cfg.nat_rules.length]);
  if (cfg.aliases.length) entries.push(["Aliases", cfg.aliases.length]);
  if (cfg.dhcp_servers.length)
    entries.push(["DHCP servers", cfg.dhcp_servers.length]);
  if (cfg.dns) entries.push(["DNS", 1]);
  if (cfg.users.length) entries.push(["Users", cfg.users.length]);
  if (cfg.groups.length) entries.push(["Groups", cfg.groups.length]);
  if (cfg.authservers.length)
    entries.push(["External auth servers", cfg.authservers.length]);
  if (cfg.sysctl.length) entries.push(["Sysctl tunables", cfg.sysctl.length]);
  if (cfg.cron.length) entries.push(["Cron jobs", cfg.cron.length]);
  if (cfg.unrecognized_sections.length)
    entries.push([
      "Other sections (raw XML)",
      cfg.unrecognized_sections.length,
    ]);

  return (
    <div className="flex flex-wrap gap-2 rounded border border-border bg-muted/30 p-2">
      <span className="text-xs text-muted-fg">
        {cfg.config_version
          ? `Config schema v${cfg.config_version}`
          : "Config"}{" "}
        ·
      </span>
      {entries.map(([title, count]) => (
        <a
          key={title}
          href={`#${sectionId(title)}`}
          className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs text-muted-fg hover:bg-muted hover:text-fg"
        >
          {title}
          <span className="text-[10px] opacity-70">({count})</span>
        </a>
      ))}
    </div>
  );
}

function sectionId(title: string) {
  return (
    "section-" + title.toLowerCase().replace(/\s+/g, "-").replace(/[()]/g, "")
  );
}

function Dl({ items }: { items: [string, React.ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
      {items.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted-fg">{k}</dt>
          <dd className="font-mono">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function Redacted() {
  return (
    <span
      title="Value redacted server-side — view raw XML tab if you truly need the plaintext"
      className="inline-flex items-center gap-1 text-muted-fg"
    >
      <Lock className="h-3 w-3" /> redacted
    </span>
  );
}

/** Value is "***redacted***" from the server? → lock glyph. Else raw. */
function RV({ v }: { v: string | null | undefined }) {
  if (v === "***redacted***") return <Redacted />;
  return <>{v || <span className="text-muted-fg">—</span>}</>;
}

function Table({
  headers,
  rows,
}: {
  headers: string[];
  rows: React.ReactNode[][];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-border text-xs uppercase text-muted-fg">
            {headers.map((h) => (
              <th key={h} className="px-2 py-1 font-normal">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-border/50 last:border-0">
              {row.map((cell, j) => (
                <td key={j} className="px-2 py-1 align-top">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------- section renderers ---------------------------------------------

function SystemPanel({ s }: { s: SystemInfo }) {
  return (
    <Dl
      items={[
        ["Hostname", <RV v={s.hostname} key="h" />],
        ["Domain", <RV v={s.domain} key="d" />],
        ["Timezone", <RV v={s.timezone} key="tz" />],
        ["DNS servers", s.dnsservers.join(", ") || "—"],
        ["Time servers", s.timeservers.join(", ") || "—"],
        [
          "Web GUI",
          s.webgui
            ? `${s.webgui.protocol ?? "?"} :${s.webgui.port ?? "?"}`
            : "—",
        ],
        ["SSH", s.enablesshd ? `enabled on :${s.sshport ?? "22"}` : "disabled"],
      ]}
    />
  );
}

function InterfacesTable({ rows }: { rows: Interface[] }) {
  return (
    <Table
      headers={["Name", "If", "Enabled", "IPv4", "IPv6", "Description"]}
      rows={rows.map((r) => [
        r.key,
        r.if_ ?? "—",
        r.enabled ? "yes" : "no",
        r.ipaddr ? `${r.ipaddr}${r.subnet ? "/" + r.subnet : ""}` : "—",
        r.ipaddrv6 ? `${r.ipaddrv6}${r.subnetv6 ? "/" + r.subnetv6 : ""}` : "—",
        r.descr ?? "—",
      ])}
    />
  );
}

function GatewaysTable({ rows }: { rows: Gateway[] }) {
  return (
    <Table
      headers={["Name", "Interface", "Gateway", "Monitor", "Default", "Descr"]}
      rows={rows.map((r) => [
        r.name,
        r.interface ?? "—",
        r.gateway ?? "—",
        r.monitor ?? "—",
        r.defaultgw ? "yes" : "",
        r.descr ?? "—",
      ])}
    />
  );
}

function StaticRoutesTable({ rows }: { rows: StaticRoute[] }) {
  return (
    <Table
      headers={["Network", "Gateway", "Disabled", "Description"]}
      rows={rows.map((r) => [
        r.network ?? "—",
        r.gateway ?? "—",
        r.disabled ? "yes" : "",
        r.descr ?? "—",
      ])}
    />
  );
}

function FirewallTable({ rows }: { rows: FirewallRule[] }) {
  return (
    <Table
      headers={[
        "#",
        "Action",
        "Iface",
        "Proto",
        "Source",
        "Destination",
        "Description",
      ]}
      rows={rows.map((r, i) => [
        i + 1,
        r.type ?? "—",
        r.interface ?? "—",
        r.protocol ?? "any",
        endpointStr(r.source),
        endpointStr(r.destination),
        <span key="d">
          {r.descr ?? "—"}
          {r.disabled && (
            <Badge tone="muted" className="ml-1">
              disabled
            </Badge>
          )}
        </span>,
      ])}
    />
  );
}

function NatTable({ rows }: { rows: NatRule[] }) {
  return (
    <Table
      headers={[
        "Kind",
        "Iface",
        "Proto",
        "Source",
        "Destination",
        "Target",
        "Local port",
        "Description",
      ]}
      rows={rows.map((r) => [
        r.kind,
        r.interface ?? "—",
        r.protocol ?? "—",
        endpointStr(r.source),
        endpointStr(r.destination),
        r.target ?? "—",
        r.local_port ?? "—",
        r.descr ?? "—",
      ])}
    />
  );
}

function endpointStr(e: {
  any_: boolean;
  network: string | null;
  address: string | null;
  port: string | null;
}) {
  if (e.any_) return "any";
  const host = e.network ?? e.address ?? "?";
  return e.port ? `${host}:${e.port}` : host;
}

function AliasesTable({ rows }: { rows: Alias[] }) {
  return (
    <Table
      headers={["Name", "Type", "Entries", "Description"]}
      rows={rows.map((r) => [
        r.name,
        r.type ?? "—",
        <span key="e" className="font-mono text-xs">
          {r.entries.join(" ") || "—"}
        </span>,
        r.descr ?? "—",
      ])}
    />
  );
}

function DhcpTable({ rows }: { rows: DhcpServer[] }) {
  return (
    <div className="space-y-3">
      {rows.map((s) => (
        <div
          key={s.interface}
          className="rounded border border-border/70 bg-muted/20 p-2"
        >
          <div className="mb-1 text-sm font-medium">
            DHCP on {s.interface}{" "}
            <Badge tone={s.enabled ? "success" : "muted"}>
              {s.enabled ? "enabled" : "disabled"}
            </Badge>
          </div>
          <Dl
            items={[
              [
                "Range",
                s.range_from && s.range_to
                  ? `${s.range_from} → ${s.range_to}`
                  : "—",
              ],
              ["Domain", s.domain ?? "—"],
              ["DNS", s.dnsservers.join(", ") || "—"],
              [
                "Static maps",
                <span key="sm">
                  {s.static_mappings.length} entr
                  {s.static_mappings.length === 1 ? "y" : "ies"}
                </span>,
              ],
            ]}
          />
          {s.static_mappings.length > 0 && (
            <div className="mt-2">
              <Table
                headers={["MAC", "IP", "Hostname", "Descr"]}
                rows={s.static_mappings.map((m) => [
                  m.mac ?? "—",
                  m.ipaddr ?? "—",
                  m.hostname ?? "—",
                  m.descr ?? "—",
                ])}
              />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function DnsPanel({ d }: { d: DnsConfig }) {
  return (
    <div className="space-y-3">
      <Dl
        items={[
          [
            "Resolver (unbound)",
            d.unbound_enabled
              ? `enabled :${d.unbound_port ?? "53"}`
              : "disabled",
          ],
          [
            "Forwarder (dnsmasq)",
            d.dnsmasq_enabled
              ? `enabled :${d.dnsmasq_port ?? "53"}`
              : "disabled",
          ],
        ]}
      />
      {d.host_overrides.length > 0 && (
        <div>
          <div className="mb-1 text-xs uppercase text-muted-fg">
            Host overrides ({d.host_overrides.length})
          </div>
          <Table
            headers={["Host", "Domain", "IP", "Description"]}
            rows={d.host_overrides.map((h) => [
              h.host ?? "—",
              h.domain ?? "—",
              h.ip ?? "—",
              h.descr ?? "—",
            ])}
          />
        </div>
      )}
      {d.domain_overrides.length > 0 && (
        <div>
          <div className="mb-1 text-xs uppercase text-muted-fg">
            Domain overrides ({d.domain_overrides.length})
          </div>
          <Table
            headers={["Domain", "IP", "Description"]}
            rows={d.domain_overrides.map((h) => [
              h.domain ?? "—",
              h.ip ?? "—",
              h.descr ?? "—",
            ])}
          />
        </div>
      )}
    </div>
  );
}

function UsersTable({ rows }: { rows: User[] }) {
  return (
    <Table
      headers={["Name", "UID", "Scope", "Groups", "Password", "Expires"]}
      rows={rows.map((u) => [
        u.name,
        u.uid ?? "—",
        u.scope ?? "—",
        u.groups.join(", ") || "—",
        <RV v={u.bcrypt_hash} key="p" />,
        u.expires ?? "—",
      ])}
    />
  );
}

function GroupsTable({ rows }: { rows: Group[] }) {
  return (
    <Table
      headers={["Name", "GID", "Scope", "Members", "Privileges"]}
      rows={rows.map((g) => [
        g.name,
        g.gid ?? "—",
        g.scope ?? "—",
        g.members.join(", ") || "—",
        <span key="p" className="font-mono text-xs">
          {g.privs.join(", ") || "—"}
        </span>,
      ])}
    />
  );
}

function AuthServersTable({ rows }: { rows: AuthServer[] }) {
  return (
    <Table
      headers={["Name", "Type", "Host", "Port", "Bind / Secret"]}
      rows={rows.map((a) => [
        a.name,
        a.type ?? "—",
        a.host ?? "—",
        a.port ?? "—",
        a.type === "ldap" ? (
          <RV v={a.ldap_bindpw} key="s" />
        ) : (
          <RV v={a.radius_secret} key="s" />
        ),
      ])}
    />
  );
}

function SysctlTable({ rows }: { rows: SysctlTunable[] }) {
  return (
    <Table
      headers={["Tunable", "Value", "Description"]}
      rows={rows.map((t) => [
        <span key="t" className="font-mono text-xs">
          {t.tunable}
        </span>,
        t.value ?? "—",
        t.descr ?? "—",
      ])}
    />
  );
}

function CronTable({ rows }: { rows: CronJob[] }) {
  return (
    <Table
      headers={["Minute", "Hour", "MDay", "Month", "WDay", "Who", "Command"]}
      rows={rows.map((c) => [
        c.minute ?? "*",
        c.hour ?? "*",
        c.mday ?? "*",
        c.month ?? "*",
        c.wday ?? "*",
        c.who ?? "—",
        <span key="c" className="font-mono text-xs">
          {c.command ?? ""}
        </span>,
      ])}
    />
  );
}

function UnrecognizedList({ rows }: { rows: RawSection[] }) {
  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-fg">
        These sections are not yet structured-parsed. They'll be promoted
        in a later release — in the meantime, the raw XML subtree is
        shown below so the data is still visible.
      </p>
      {rows.map((s) => (
        <details
          key={s.tag}
          className="rounded border border-border/70 bg-muted/20 p-2 text-sm"
        >
          <summary className="cursor-pointer font-mono text-xs">
            &lt;{s.tag}&gt;
          </summary>
          <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-xs">
            {s.xml}
          </pre>
        </details>
      ))}
    </div>
  );
}
