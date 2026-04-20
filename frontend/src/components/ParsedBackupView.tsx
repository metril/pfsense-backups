import { useState } from "react";
import { ChevronDown, ChevronRight, Lock } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { useParsedBackup } from "@/api/queries";
import type {
  Alias,
  AuthServer,
  Bridge,
  CaptivePortalZone,
  AcmeConfig,
  Certificate,
  CertificateAuthority,
  HaProxyConfig,
  InstalledPackages,
  PfBlockerNgConfig,
  SuricataConfig,
  UnknownPackage,
  CronJob,
  DhcpRelayConfig,
  DhcpServer,
  DnsConfig,
  DnShaperPipe,
  FirewallRule,
  Gateway,
  Group,
  HaSync,
  Interface,
  IpsecPhase1,
  IpsecPhase2,
  IpsecPskEntry,
  LoadBalancerPool,
  LoadBalancerVirtualServer,
  NatRule,
  NtpdConfig,
  OpenVpnClient,
  OpenVpnCsc,
  OpenVpnServer,
  ParsedConfig,
  Ppp,
  QinQ,
  RawSection,
  Schedule,
  ShaperQueue,
  SnmpdConfig,
  StaticRoute,
  SyslogConfig,
  SysctlTunable,
  SystemInfo,
  Tunnel,
  User,
  VirtualIP,
  Vlan,
  WolHost,
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
        {data.vlans.length > 0 && (
          <Section title="VLANs" count={data.vlans.length}>
            <VlansTable rows={data.vlans} />
          </Section>
        )}
        {data.bridges.length > 0 && (
          <Section title="Bridges" count={data.bridges.length}>
            <BridgesTable rows={data.bridges} />
          </Section>
        )}
        {data.gifs.length > 0 && (
          <Section title="GIF tunnels" count={data.gifs.length}>
            <TunnelsTable rows={data.gifs} />
          </Section>
        )}
        {data.gres.length > 0 && (
          <Section title="GRE tunnels" count={data.gres.length}>
            <TunnelsTable rows={data.gres} />
          </Section>
        )}
        {data.ppps.length > 0 && (
          <Section title="PPP interfaces" count={data.ppps.length}>
            <PppsTable rows={data.ppps} />
          </Section>
        )}
        {data.qinqs.length > 0 && (
          <Section title="QinQ" count={data.qinqs.length}>
            <QinqTable rows={data.qinqs} />
          </Section>
        )}
        {data.wol.length > 0 && (
          <Section title="Wake-on-LAN" count={data.wol.length}>
            <WolTable rows={data.wol} />
          </Section>
        )}
        {data.virtual_ips.length > 0 && (
          <Section title="Virtual IPs / CARP" count={data.virtual_ips.length}>
            <VirtualIpsTable rows={data.virtual_ips} />
          </Section>
        )}
        {data.hasync && (
          <Section title="HA / CARP sync" count={1}>
            <HaSyncPanel h={data.hasync} />
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
        {data.dhcp_relays.length > 0 && (
          <Section title="DHCP relay" count={data.dhcp_relays.length}>
            <DhcpRelayTable rows={data.dhcp_relays} />
          </Section>
        )}
        {data.ntpd && (
          <Section title="NTP server" count={1}>
            <NtpdPanel n={data.ntpd} />
          </Section>
        )}
        {data.snmpd && (
          <Section title="SNMP" count={1}>
            <SnmpdPanel s={data.snmpd} />
          </Section>
        )}
        {data.syslog && (
          <Section title="Remote syslog" count={1}>
            <SyslogPanel s={data.syslog} />
          </Section>
        )}
        {data.schedules.length > 0 && (
          <Section title="Schedules" count={data.schedules.length}>
            <SchedulesTable rows={data.schedules} />
          </Section>
        )}
        {data.shaper_queues.length > 0 && (
          <Section title="Traffic shaper queues" count={data.shaper_queues.length}>
            <ShaperTable rows={data.shaper_queues} />
          </Section>
        )}
        {data.dnshaper_pipes.length > 0 && (
          <Section title="Limiter pipes" count={data.dnshaper_pipes.length}>
            <DnShaperTable rows={data.dnshaper_pipes} />
          </Section>
        )}
        {(data.lb_pools.length > 0 || data.lb_virtual_servers.length > 0) && (
          <Section
            title="Load balancer"
            count={data.lb_pools.length + data.lb_virtual_servers.length}
          >
            <LoadBalancerPanel
              pools={data.lb_pools}
              vservers={data.lb_virtual_servers}
            />
          </Section>
        )}
        {data.captive_portal_zones.length > 0 && (
          <Section
            title="Captive portal"
            count={data.captive_portal_zones.length}
          >
            <CaptivePortalTable rows={data.captive_portal_zones} />
          </Section>
        )}
        {data.openvpn_servers.length > 0 && (
          <Section title="OpenVPN servers" count={data.openvpn_servers.length}>
            <OpenVpnServersTable rows={data.openvpn_servers} />
          </Section>
        )}
        {data.openvpn_clients.length > 0 && (
          <Section title="OpenVPN clients" count={data.openvpn_clients.length}>
            <OpenVpnClientsTable rows={data.openvpn_clients} />
          </Section>
        )}
        {data.openvpn_cscs.length > 0 && (
          <Section
            title="OpenVPN client-specific overrides"
            count={data.openvpn_cscs.length}
          >
            <OpenVpnCscTable rows={data.openvpn_cscs} />
          </Section>
        )}
        {data.ipsec_phase1.length > 0 && (
          <Section title="IPsec — phase 1" count={data.ipsec_phase1.length}>
            <IpsecPhase1Table rows={data.ipsec_phase1} />
          </Section>
        )}
        {data.ipsec_phase2.length > 0 && (
          <Section title="IPsec — phase 2" count={data.ipsec_phase2.length}>
            <IpsecPhase2Table rows={data.ipsec_phase2} />
          </Section>
        )}
        {data.ipsec_psks.length > 0 && (
          <Section
            title="IPsec — pre-shared keys"
            count={data.ipsec_psks.length}
          >
            <IpsecPskTable rows={data.ipsec_psks} />
          </Section>
        )}
        {data.certificate_authorities.length > 0 && (
          <Section
            title="Certificate authorities"
            count={data.certificate_authorities.length}
          >
            <CATable rows={data.certificate_authorities} />
          </Section>
        )}
        {data.certificates.length > 0 && (
          <Section title="Certificates" count={data.certificates.length}>
            <CertsTable rows={data.certificates} />
          </Section>
        )}
        {data.installedpackages && (
          <Section
            title="Installed packages"
            count={packageCount(data.installedpackages)}
          >
            <PackagesPanel ip={data.installedpackages} />
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
  if (cfg.vlans.length) entries.push(["VLANs", cfg.vlans.length]);
  if (cfg.bridges.length) entries.push(["Bridges", cfg.bridges.length]);
  if (cfg.gifs.length) entries.push(["GIF tunnels", cfg.gifs.length]);
  if (cfg.gres.length) entries.push(["GRE tunnels", cfg.gres.length]);
  if (cfg.ppps.length) entries.push(["PPP interfaces", cfg.ppps.length]);
  if (cfg.qinqs.length) entries.push(["QinQ", cfg.qinqs.length]);
  if (cfg.wol.length) entries.push(["Wake-on-LAN", cfg.wol.length]);
  if (cfg.virtual_ips.length)
    entries.push(["Virtual IPs / CARP", cfg.virtual_ips.length]);
  if (cfg.hasync) entries.push(["HA / CARP sync", 1]);
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
  if (cfg.dhcp_relays.length)
    entries.push(["DHCP relay", cfg.dhcp_relays.length]);
  if (cfg.ntpd) entries.push(["NTP server", 1]);
  if (cfg.snmpd) entries.push(["SNMP", 1]);
  if (cfg.syslog) entries.push(["Remote syslog", 1]);
  if (cfg.schedules.length) entries.push(["Schedules", cfg.schedules.length]);
  if (cfg.shaper_queues.length)
    entries.push(["Traffic shaper queues", cfg.shaper_queues.length]);
  if (cfg.dnshaper_pipes.length)
    entries.push(["Limiter pipes", cfg.dnshaper_pipes.length]);
  if (cfg.lb_pools.length || cfg.lb_virtual_servers.length)
    entries.push([
      "Load balancer",
      cfg.lb_pools.length + cfg.lb_virtual_servers.length,
    ]);
  if (cfg.captive_portal_zones.length)
    entries.push(["Captive portal", cfg.captive_portal_zones.length]);
  if (cfg.openvpn_servers.length)
    entries.push(["OpenVPN servers", cfg.openvpn_servers.length]);
  if (cfg.openvpn_clients.length)
    entries.push(["OpenVPN clients", cfg.openvpn_clients.length]);
  if (cfg.openvpn_cscs.length)
    entries.push([
      "OpenVPN client-specific overrides",
      cfg.openvpn_cscs.length,
    ]);
  if (cfg.ipsec_phase1.length)
    entries.push(["IPsec — phase 1", cfg.ipsec_phase1.length]);
  if (cfg.ipsec_phase2.length)
    entries.push(["IPsec — phase 2", cfg.ipsec_phase2.length]);
  if (cfg.ipsec_psks.length)
    entries.push(["IPsec — pre-shared keys", cfg.ipsec_psks.length]);
  if (cfg.certificate_authorities.length)
    entries.push([
      "Certificate authorities",
      cfg.certificate_authorities.length,
    ]);
  if (cfg.certificates.length)
    entries.push(["Certificates", cfg.certificates.length]);
  if (cfg.installedpackages)
    entries.push(["Installed packages", packageCount(cfg.installedpackages)]);
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

function VlansTable({ rows }: { rows: Vlan[] }) {
  return (
    <Table
      headers={["Parent", "Tag", "PCP", "Device", "Description"]}
      rows={rows.map((v) => [
        v.if_ ?? "—",
        v.tag ?? "—",
        v.pcp ?? "—",
        v.vlanif ?? "—",
        v.descr ?? "—",
      ])}
    />
  );
}

function BridgesTable({ rows }: { rows: Bridge[] }) {
  return (
    <Table
      headers={["Bridge", "Members", "STP", "Description"]}
      rows={rows.map((b) => [
        b.bridgeif,
        b.members.join(", ") || "—",
        b.enablestp ? "yes" : "",
        b.descr ?? "—",
      ])}
    />
  );
}

function TunnelsTable({ rows }: { rows: Tunnel[] }) {
  return (
    <Table
      headers={["Device", "Outer if", "Remote", "Tunnel local", "Tunnel remote", "Description"]}
      rows={rows.map((t) => [
        t.name,
        t.if_ ?? "—",
        t.remote_addr ?? "—",
        t.tunnel_local_addr ?? "—",
        t.tunnel_remote_addr ?? t.tunnel_remote_net ?? "—",
        t.descr ?? "—",
      ])}
    />
  );
}

function PppsTable({ rows }: { rows: Ppp[] }) {
  return (
    <Table
      headers={["Type", "Interface", "Username", "Provider", "Description"]}
      rows={rows.map((p) => [
        p.type ?? "—",
        p.if_ ?? "—",
        p.username ?? "—",
        p.provider ?? "—",
        p.descr ?? "—",
      ])}
    />
  );
}

function QinqTable({ rows }: { rows: QinQ[] }) {
  return (
    <Table
      headers={["Parent", "Outer tag", "Inner tags", "Description"]}
      rows={rows.map((q) => [
        q.if_ ?? "—",
        q.tag ?? "—",
        q.members.join(", ") || "—",
        q.descr ?? "—",
      ])}
    />
  );
}

function WolTable({ rows }: { rows: WolHost[] }) {
  return (
    <Table
      headers={["MAC", "Interface", "Description"]}
      rows={rows.map((w) => [w.mac, w.interface ?? "—", w.descr ?? "—"])}
    />
  );
}

function VirtualIpsTable({ rows }: { rows: VirtualIP[] }) {
  return (
    <Table
      headers={["Mode", "Interface", "Subnet", "VHID", "CARP pwd", "Description"]}
      rows={rows.map((v) => [
        v.mode ?? "—",
        v.interface ?? "—",
        v.subnet
          ? `${v.subnet}${v.subnet_bits ? "/" + v.subnet_bits : ""}`
          : "—",
        v.vhid ?? "—",
        v.password === "***redacted***" ? <Redacted /> : "—",
        v.descr ?? "—",
      ])}
    />
  );
}

function HaSyncPanel({ h }: { h: HaSync }) {
  const synced = [
    ["rules", h.synchronizerules],
    ["nat", h.synchronizenat],
    ["aliases", h.synchronizealiases],
    ["schedules", h.synchronizeschedules],
    ["dhcp", h.synchronizedhcpd],
    ["dhcp relay", h.synchronizedhcrelay],
    ["dns", h.synchronizedns],
    ["openvpn", h.synchronizeopenvpn],
    ["ipsec", h.synchronizeipsec],
    ["users", h.synchronizeusers],
    ["authservers", h.synchronizeauthservers],
    ["certs", h.synchronizecerts],
  ]
    .filter(([, on]) => on)
    .map(([label]) => label as string);
  return (
    <Dl
      items={[
        [
          "pfsync",
          h.pfsyncenabled
            ? `enabled on ${h.pfsyncinterface ?? "?"} (peer ${h.pfsyncpeerip ?? "?"})`
            : "disabled",
        ],
        ["XMLRPC peer", h.synchronizetoip ?? "—"],
        ["Sync user", h.username ?? "—"],
        ["Sync password", <RV v={h.password} key="p" />],
        ["Sections synced", synced.length ? synced.join(", ") : "—"],
      ]}
    />
  );
}

function DhcpRelayTable({ rows }: { rows: DhcpRelayConfig[] }) {
  return (
    <Table
      headers={["Kind", "Enabled", "Interfaces", "Relay to", "Agent option"]}
      rows={rows.map((r) => [
        r.kind,
        r.enable ? "yes" : "no",
        r.interface.join(", ") || "—",
        r.server.join(", ") || "—",
        r.agentoption ? "yes" : "no",
      ])}
    />
  );
}

function NtpdPanel({ n }: { n: NtpdConfig }) {
  return (
    <Dl
      items={[
        ["Enabled", n.enable ? "yes" : "no"],
        ["Interfaces", n.interfaces.join(", ") || "—"],
        ["Time servers", n.timeservers.join(", ") || "—"],
        ["Orphan mode", n.orphan ?? "—"],
        ["Leap second policy", n.leapsec ?? "—"],
      ]}
    />
  );
}

function SnmpdPanel({ s }: { s: SnmpdConfig }) {
  return (
    <Dl
      items={[
        ["Enabled", s.enable ? "yes" : "no"],
        ["Location", s.syslocation ?? "—"],
        ["Contact", s.syscontact ?? "—"],
        ["Poll port", s.pollport ?? "—"],
        ["Bind", s.bindlan ? "LAN" : s.bindip ?? "—"],
        ["RO community", <RV v={s.rocommunity} key="ro" />],
        ["RW community", <RV v={s.rwcommunity} key="rw" />],
        [
          "Traps",
          s.trapenable
            ? `${s.trapserver ?? "?"}:${s.trapserverport ?? "?"}`
            : "disabled",
        ],
      ]}
    />
  );
}

function SyslogPanel({ s }: { s: SyslogConfig }) {
  const filters = [
    ["system", s.system],
    ["filter", s.filter_],
    ["dhcp", s.dhcp],
    ["portalauth", s.portalauth],
    ["vpn", s.vpn],
    ["dpinger", s.dpinger],
    ["hostapd", s.hostapd],
    ["resolver", s.resolver],
    ["ppp", s.ppp],
    ["routing", s.routing],
    ["ntpd", s.ntpd],
  ]
    .filter(([, on]) => on)
    .map(([k]) => k as string);
  return (
    <Dl
      items={[
        ["Enabled", s.enable ? "yes" : "no"],
        ["Reverse display", s.reverse ? "yes" : "no"],
        ["Local buffer entries", s.nentries ?? "—"],
        [
          "Remote destinations",
          s.hosts.length > 0 ? s.hosts.map((h) => h.host).join(", ") : "—",
        ],
        ["Filters", filters.length ? filters.join(", ") : "—"],
      ]}
    />
  );
}

function SchedulesTable({ rows }: { rows: Schedule[] }) {
  return (
    <Table
      headers={["Name", "Description", "Time ranges"]}
      rows={rows.map((s) => [
        s.name,
        s.descr ?? "—",
        <span key="tr" className="font-mono text-xs">
          {s.time_ranges.join(" · ") || "—"}
        </span>,
      ])}
    />
  );
}

function ShaperTable({ rows }: { rows: ShaperQueue[] }) {
  return (
    <Table
      headers={["Name", "Interface", "Priority", "Bandwidth", "Description"]}
      rows={rows.map((q) => [
        q.name,
        q.interface ?? "—",
        q.priority ?? "—",
        q.bandwidth
          ? `${q.bandwidth}${q.bandwidthtype ? " " + q.bandwidthtype : ""}`
          : "—",
        q.descr ?? "—",
      ])}
    />
  );
}

function DnShaperTable({ rows }: { rows: DnShaperPipe[] }) {
  return (
    <Table
      headers={["Name", "Number", "Bandwidth", "Description"]}
      rows={rows.map((p) => [
        p.name,
        p.number ?? "—",
        p.bandwidth
          ? `${p.bandwidth}${p.bandwidthtype ? " " + p.bandwidthtype : ""}`
          : "—",
        p.descr ?? "—",
      ])}
    />
  );
}

function LoadBalancerPanel({
  pools,
  vservers,
}: {
  pools: LoadBalancerPool[];
  vservers: LoadBalancerVirtualServer[];
}) {
  return (
    <div className="space-y-3">
      {pools.length > 0 && (
        <div>
          <div className="mb-1 text-xs uppercase text-muted-fg">Pools</div>
          <Table
            headers={["Name", "Behaviour", "Port", "Monitor", "Members", "Description"]}
            rows={pools.map((p) => [
              p.name,
              p.behaviour ?? "—",
              p.port ?? "—",
              p.monitor ?? "—",
              p.servers
                .map((m) => (m.port ? `${m.ip}:${m.port}` : m.ip ?? "?"))
                .join(", ") || "—",
              p.descr ?? "—",
            ])}
          />
        </div>
      )}
      {vservers.length > 0 && (
        <div>
          <div className="mb-1 text-xs uppercase text-muted-fg">
            Virtual servers
          </div>
          <Table
            headers={["Name", "Address", "Port", "Mode", "Pool", "Description"]}
            rows={vservers.map((v) => [
              v.name,
              v.ipaddr ?? "—",
              v.port ?? "—",
              v.mode ?? "—",
              v.poolname ?? "—",
              v.descr ?? "—",
            ])}
          />
        </div>
      )}
    </div>
  );
}

function CaptivePortalTable({ rows }: { rows: CaptivePortalZone[] }) {
  return (
    <Table
      headers={["Zone", "Zone ID", "Enabled", "Interfaces", "Auth", "RADIUS", "Redirect"]}
      rows={rows.map((z) => [
        z.zone,
        z.zoneid ?? "—",
        z.enable ? "yes" : "no",
        z.interfaces.join(", ") || "—",
        z.auth_method ?? "—",
        z.radius_secret === "***redacted***" ? <Redacted /> : "—",
        z.redirurl ?? "—",
      ])}
    />
  );
}

function OpenVpnServersTable({ rows }: { rows: OpenVpnServer[] }) {
  return (
    <Table
      headers={[
        "#",
        "Description",
        "Mode",
        "Proto / port",
        "Tunnel",
        "Cipher",
        "TLS",
      ]}
      rows={rows.map((s) => [
        s.vpnid,
        s.description ?? "—",
        s.mode ?? "—",
        `${s.protocol ?? "?"} :${s.local_port ?? "?"}`,
        s.tunnel_network ?? s.tunnel_networkv6 ?? "—",
        s.crypto ?? "—",
        s.tls === "***redacted***" ? <Redacted /> : "—",
      ])}
    />
  );
}

function OpenVpnClientsTable({ rows }: { rows: OpenVpnClient[] }) {
  return (
    <Table
      headers={["#", "Description", "Mode", "Server", "Tunnel", "Cipher", "TLS"]}
      rows={rows.map((c) => [
        c.vpnid,
        c.description ?? "—",
        c.mode ?? "—",
        c.server_addr
          ? `${c.server_addr}:${c.server_port ?? "?"}`
          : "—",
        c.tunnel_network ?? "—",
        c.crypto ?? "—",
        c.tls === "***redacted***" ? <Redacted /> : "—",
      ])}
    />
  );
}

function OpenVpnCscTable({ rows }: { rows: OpenVpnCsc[] }) {
  return (
    <Table
      headers={[
        "Common name",
        "Disabled",
        "Servers",
        "Tunnel net",
        "Description",
      ]}
      rows={rows.map((c) => [
        c.common_name,
        c.disable ? "yes" : "",
        c.server_list.join(", ") || "—",
        c.tunnel_network ?? "—",
        c.description ?? "—",
      ])}
    />
  );
}

function IpsecPhase1Table({ rows }: { rows: IpsecPhase1[] }) {
  return (
    <Table
      headers={[
        "IKE id",
        "Type",
        "Remote gw",
        "Auth",
        "PSK",
        "Encryption set",
        "Description",
      ]}
      rows={rows.map((p) => [
        p.ikeid,
        p.iketype ?? "—",
        p.remote_gateway ?? "—",
        p.authentication_method ?? "—",
        p.pre_shared_key === "***redacted***" ? <Redacted /> : "—",
        <span key="e" className="font-mono text-xs">
          {p.encryption_set.join(", ") || "—"}
        </span>,
        p.descr ?? "—",
      ])}
    />
  );
}

function IpsecPhase2Table({ rows }: { rows: IpsecPhase2[] }) {
  return (
    <Table
      headers={[
        "Phase2 id",
        "IKE id",
        "Mode",
        "Local",
        "Remote",
        "Encryption set",
        "Description",
      ]}
      rows={rows.map((p) => [
        p.uniqid,
        p.ikeid ?? "—",
        p.mode ?? "—",
        p.local_address
          ? `${p.local_address}${p.local_netbits ? "/" + p.local_netbits : ""}`
          : "—",
        p.remote_address
          ? `${p.remote_address}${p.remote_netbits ? "/" + p.remote_netbits : ""}`
          : "—",
        <span key="e" className="font-mono text-xs">
          {p.encryption_set.join(", ") || "—"}
        </span>,
        p.descr ?? "—",
      ])}
    />
  );
}

function IpsecPskTable({ rows }: { rows: IpsecPskEntry[] }) {
  return (
    <Table
      headers={["Identifier", "Type", "PSK"]}
      rows={rows.map((k) => [
        k.ident ?? "—",
        k.ident_type ?? "—",
        k.pre_shared_key === "***redacted***" ? <Redacted /> : "—",
      ])}
    />
  );
}

function CATable({ rows }: { rows: CertificateAuthority[] }) {
  return (
    <Table
      headers={["CN / refid", "Description", "Issuer", "Expires", "Private key"]}
      rows={rows.map((c) => [
        <CertIdentity key="i" refid={c.refid} meta={c.metadata} />,
        c.descr ?? "—",
        c.metadata?.issuer_cn ?? "—",
        <ExpiryCell key="e" meta={c.metadata} />,
        c.prv === "***redacted***" ? <Redacted /> : "—",
      ])}
    />
  );
}

function CertsTable({ rows }: { rows: Certificate[] }) {
  return (
    <Table
      headers={[
        "CN / refid",
        "Description",
        "Type",
        "SANs",
        "Issuer",
        "Expires",
        "Private key",
      ]}
      rows={rows.map((c) => [
        <CertIdentity key="i" refid={c.refid} meta={c.metadata} />,
        c.descr ?? "—",
        c.type ?? "—",
        <SansCell key="s" meta={c.metadata} />,
        c.metadata?.issuer_cn ?? "—",
        <ExpiryCell key="e" meta={c.metadata} />,
        c.prv === "***redacted***" ? <Redacted /> : "—",
      ])}
    />
  );
}

function CertIdentity({
  refid,
  meta,
}: {
  refid: string;
  meta: { subject_cn: string | null } | null;
}) {
  if (meta?.subject_cn) {
    return (
      <div className="leading-tight">
        <div>{meta.subject_cn}</div>
        <div className="font-mono text-xs text-muted-fg">{refid}</div>
      </div>
    );
  }
  return (
    <span className="font-mono text-xs">{refid}</span>
  );
}

function SansCell({ meta }: { meta: { sans: string[] } | null }) {
  if (!meta || meta.sans.length === 0) return <>—</>;
  if (meta.sans.length <= 2) {
    return <span className="text-xs">{meta.sans.join(", ")}</span>;
  }
  return (
    <details>
      <summary className="cursor-pointer text-xs">
        {meta.sans.length} entries
      </summary>
      <div className="mt-1 text-xs">
        {meta.sans.map((s) => (
          <div key={s} className="font-mono">
            {s}
          </div>
        ))}
      </div>
    </details>
  );
}

function ExpiryCell({
  meta,
}: {
  meta: { not_after: string | null } | null;
}) {
  if (!meta?.not_after) return <>—</>;
  const when = new Date(meta.not_after);
  const now = new Date();
  const diffDays = Math.floor(
    (when.getTime() - now.getTime()) / (1000 * 60 * 60 * 24),
  );
  const isoDate = meta.not_after.slice(0, 10);
  if (diffDays < 0) {
    return (
      <span className="text-danger" title={`expired on ${isoDate}`}>
        expired ({isoDate})
      </span>
    );
  }
  if (diffDays < 30) {
    return (
      <span className="text-warn" title={`expires on ${isoDate}`}>
        {isoDate} ({diffDays}d)
      </span>
    );
  }
  return <span title={`expires on ${isoDate}`}>{isoDate}</span>;
}

function packageCount(ip: InstalledPackages): number {
  let n = 0;
  if (ip.pfblockerng) n += 1;
  if (ip.haproxy) n += 1;
  if (ip.suricata) n += 1;
  if (ip.acme) n += 1;
  n += ip.unknown.length;
  return n;
}

function PackagesPanel({ ip }: { ip: InstalledPackages }) {
  return (
    <div className="space-y-4">
      {ip.pfblockerng && <PfBlockerNgPanel p={ip.pfblockerng} />}
      {ip.haproxy && <HaProxyPanel p={ip.haproxy} />}
      {ip.suricata && <SuricataPanel p={ip.suricata} />}
      {ip.acme && <AcmePanel p={ip.acme} />}
      {ip.unknown.length > 0 && <UnknownPackagesList rows={ip.unknown} />}
    </div>
  );
}

function PackageCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded border border-border/70 bg-muted/20 p-2">
      <div className="mb-1 text-sm font-medium">{title}</div>
      {children}
    </div>
  );
}

function PfBlockerNgPanel({ p }: { p: PfBlockerNgConfig }) {
  return (
    <PackageCard title="pfBlockerNG">
      <Dl
        items={[
          ["Enabled", p.enable_pfblockerng ? "yes" : "no"],
          ["Interface", p.pfb_interface ?? "—"],
          ["IP rules", p.ip_enabled ? `yes${p.ipv6_enabled ? " (+ IPv6)" : ""}` : "no"],
          [
            "DNSBL",
            p.dnsbl_enabled
              ? `${p.dnsbl_mode ?? "?"}:${p.dnsbl_port ?? "?"}`
              : "disabled",
          ],
          [
            "MaxMind key",
            p.maxmind_key_configured ? <Redacted /> : "not set",
          ],
        ]}
      />
      {p.feeds.length > 0 && (
        <div className="mt-2">
          <div className="mb-1 text-xs uppercase text-muted-fg">
            Feeds ({p.feeds.length})
          </div>
          <Table
            headers={["Header", "State", "Action", "URL"]}
            rows={p.feeds.map((f) => [
              f.header ?? "—",
              f.state ?? "—",
              f.action ?? "—",
              <span key="u" className="break-all font-mono text-xs">
                {f.url ?? "—"}
              </span>,
            ])}
          />
        </div>
      )}
    </PackageCard>
  );
}

function HaProxyPanel({ p }: { p: HaProxyConfig }) {
  return (
    <PackageCard title="HAProxy">
      <Dl
        items={[
          ["Enabled", p.enable ? "yes" : "no"],
          ["Remote syslog", p.remotesyslog ?? "—"],
        ]}
      />
      {p.frontends.length > 0 && (
        <div className="mt-2">
          <div className="mb-1 text-xs uppercase text-muted-fg">
            Frontends ({p.frontends.length})
          </div>
          <Table
            headers={["Name", "Type", "Listen", "Default backend", "SSL", "Status"]}
            rows={p.frontends.map((f) => [
              f.name,
              f.type ?? "—",
              f.addresses.join(", ") || f.extaddr || "—",
              f.default_backend ?? "—",
              f.ssl ? "yes" : "no",
              f.status ?? "—",
            ])}
          />
        </div>
      )}
      {p.backends.length > 0 && (
        <div className="mt-2">
          <div className="mb-1 text-xs uppercase text-muted-fg">
            Backends ({p.backends.length})
          </div>
          <Table
            headers={["Name", "Balance", "Check", "Servers"]}
            rows={p.backends.map((b) => [
              b.name,
              b.balance ?? "—",
              b.check_type ?? "—",
              <span key="s" className="text-xs">
                {b.servers
                  .map((s) =>
                    `${s.name} ${s.address ?? "?"}:${s.port ?? "?"}${s.password === "***redacted***" ? " 🔒" : ""}`,
                  )
                  .join(", ") || "—"}
              </span>,
            ])}
          />
        </div>
      )}
    </PackageCard>
  );
}

function SuricataPanel({ p }: { p: SuricataConfig }) {
  return (
    <PackageCard title="Suricata IDS/IPS">
      <Dl
        items={[
          ["Stats collection", p.enable_stats ? "yes" : "no"],
          [
            "Ruleset key (oinkcode)",
            p.oinkmaster_configured ? <Redacted /> : "not set",
          ],
        ]}
      />
      {p.interfaces.length > 0 && (
        <div className="mt-2">
          <div className="mb-1 text-xs uppercase text-muted-fg">
            Interfaces ({p.interfaces.length})
          </div>
          <Table
            headers={["Interface", "Enabled", "Block", "IPS mode", "Categories"]}
            rows={p.interfaces.map((i) => [
              i.interface ?? i.uuid,
              i.enable ? "yes" : "no",
              i.blockoffenders7 ? "yes" : "no",
              i.ips_mode ?? "—",
              <span key="c" className="font-mono text-xs">
                {i.categories.length ? `${i.categories.length} enabled` : "—"}
              </span>,
            ])}
          />
        </div>
      )}
      {p.passlists.length > 0 && (
        <div className="mt-2">
          <div className="mb-1 text-xs uppercase text-muted-fg">
            Pass lists ({p.passlists.length})
          </div>
          <Table
            headers={["Name", "Entries", "Description"]}
            rows={p.passlists.map((pl) => [
              pl.name,
              pl.entries.length,
              pl.descr ?? "—",
            ])}
          />
        </div>
      )}
    </PackageCard>
  );
}

function AcmePanel({ p }: { p: AcmeConfig }) {
  return (
    <PackageCard title="ACME (Let's Encrypt)">
      <Dl
        items={[
          ["Enabled", p.enable ? "yes" : "no"],
          ["Write cert log", p.writecert_log ? "yes" : "no"],
        ]}
      />
      {p.account_keys.length > 0 && (
        <div className="mt-2">
          <div className="mb-1 text-xs uppercase text-muted-fg">
            Account keys ({p.account_keys.length})
          </div>
          <Table
            headers={["Name", "Server", "Email", "Private key"]}
            rows={p.account_keys.map((k) => [
              k.name,
              k.acmeserver ?? "—",
              k.email ?? "—",
              k.accountkey === "***redacted***" ? <Redacted /> : "—",
            ])}
          />
        </div>
      )}
      {p.certificates.length > 0 && (
        <div className="mt-2">
          <div className="mb-1 text-xs uppercase text-muted-fg">
            Certificates ({p.certificates.length})
          </div>
          <Table
            headers={["Name", "Account", "Key length", "SANs"]}
            rows={p.certificates.map((c) => [
              c.name,
              c.acmeaccount ?? "—",
              c.keylength ?? "—",
              <span key="s" className="text-xs">
                {c.san_list.join(", ") || "—"}
              </span>,
            ])}
          />
        </div>
      )}
    </PackageCard>
  );
}

function UnknownPackagesList({ rows }: { rows: UnknownPackage[] }) {
  return (
    <PackageCard title={`Other packages (${rows.length})`}>
      <p className="mb-2 text-xs text-muted-fg">
        These packages aren't yet structured-parsed — raw XML subtree is
        available below for reference.
      </p>
      <div className="space-y-2">
        {rows.map((u) => (
          <details
            key={u.tag}
            className="rounded border border-border/50 bg-bg p-2 text-sm"
          >
            <summary className="cursor-pointer font-mono text-xs">
              &lt;{u.tag}&gt; &nbsp;
              <span className="text-muted-fg">
                {u.entry_count} child entr{u.entry_count === 1 ? "y" : "ies"}
              </span>
            </summary>
            <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-xs">
              {u.xml}
            </pre>
          </details>
        ))}
      </div>
    </PackageCard>
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
