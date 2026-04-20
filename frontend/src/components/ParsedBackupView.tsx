import { memo } from "react";
import { Lock } from "lucide-react";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { useParsedBackup } from "@/api/queries";
import {
  interfaceChipClasses,
  interfaceLabel,
} from "@/lib/ifaceColor";
import { cn } from "@/lib/cn";
import { sectionGroup, type SectionGroup } from "@/lib/sectionGroup";
import type {
  Alias,
  AuthServer,
  Bridge,
  CaptivePortalZone,
  AcmeConfig,
  Certificate,
  CertificateAuthority,
  CertificateRevocationList,
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
  DyndnsEntry,
  FirewallRule,
  FreeRadiusConfig,
  FrrConfig,
  FtpProxyConfig,
  Gateway,
  GatewayGroup,
  Group,
  HaSync,
  IgmpProxyEntry,
  Interface,
  IpsecPhase1,
  IpsecPhase2,
  IpsecPskEntry,
  Lagg,
  LoadBalancerPool,
  LoadBalancerVirtualServer,
  NatRule,
  NotificationConfig,
  NtpdConfig,
  OpenVpnClient,
  OpenVpnCsc,
  OpenVpnServer,
  ParsedConfig,
  Ppp,
  QinQ,
  RadvdInterfaceConfig,
  RawSection,
  Schedule,
  ShaperQueue,
  SnmpdConfig,
  SquidBundle,
  StaticRoute,
  SyslogConfig,
  SysctlTunable,
  SystemInfo,
  TelegrafConfig,
  Tunnel,
  UpsConfig,
  User,
  VirtualIP,
  VoucherRoll,
  ZabbixBundle,
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
      <div className="p-6">
        <Alert tone="danger" title="Could not parse config">
          {String(error)}
        </Alert>
      </div>
    );
  if (!data) return null;

  return (
    <div className="h-full overflow-auto p-4">
      <div className="mx-auto max-w-[1400px]">
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
        {data.laggs.length > 0 && (
          <Section title="LAGG" count={data.laggs.length}>
            <LaggsTable rows={data.laggs} />
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
        {data.gateway_groups.length > 0 && (
          <Section
            title="Gateway groups"
            count={data.gateway_groups.length}
          >
            <GatewayGroupsTable rows={data.gateway_groups} />
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
        {data.dyndns_entries.length > 0 && (
          <Section title="Dynamic DNS" count={data.dyndns_entries.length}>
            <DyndnsTable rows={data.dyndns_entries} />
          </Section>
        )}
        {data.igmpproxy_entries.length > 0 && (
          <Section title="IGMP proxy" count={data.igmpproxy_entries.length}>
            <IgmpProxyTable rows={data.igmpproxy_entries} />
          </Section>
        )}
        {data.radvd_interfaces.length > 0 && (
          <Section
            title="Router Advertisements (IPv6)"
            count={data.radvd_interfaces.length}
          >
            <RadvdTable rows={data.radvd_interfaces} />
          </Section>
        )}
        {data.notifications && (
          <Section title="Notifications" count={1}>
            <NotificationsPanel n={data.notifications} />
          </Section>
        )}
        {data.ups && (
          <Section title="UPS monitoring" count={1}>
            <UpsPanel u={data.ups} />
          </Section>
        )}
        {data.voucher_rolls.length > 0 && (
          <Section
            title="Captive-portal vouchers"
            count={data.voucher_rolls.length}
          >
            <VoucherTable rows={data.voucher_rolls} />
          </Section>
        )}
        {data.ftpproxy && (
          <Section title="FTP proxy" count={1}>
            <FtpProxyPanel f={data.ftpproxy} />
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
        {data.crls.length > 0 && (
          <Section
            title="Certificate revocation lists"
            count={data.crls.length}
          >
            <CrlTable rows={data.crls} />
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
    </div>
  );
}

// ---------- primitives -----------------------------------------------------

/** Title → ParsedConfig field key, used only to look up the section
 *  group color. Kept here (instead of on each call site) because every
 *  title is hard-coded above and this keeps the rewrite small. When a
 *  new section is added, add an entry here to get it colored;
 *  otherwise it falls back to neutral. */
const TITLE_TO_KEY: Record<string, string> = {
  System: "system",
  "Last revision": "revision",
  "Sysctl tunables": "sysctl",
  "Cron jobs": "cron",
  Notifications: "notifications",
  Interfaces: "interfaces",
  VLANs: "vlans",
  Bridges: "bridges",
  "GIF tunnels": "gifs",
  "GRE tunnels": "gres",
  "PPP interfaces": "ppps",
  QinQ: "qinqs",
  LAGG: "laggs",
  "Wake-on-LAN": "wol",
  Gateways: "gateways",
  "Gateway groups": "gateway_groups",
  "Static routes": "static_routes",
  "Virtual IPs / CARP": "virtual_ips",
  "HA / CARP sync": "hasync",
  "Firewall rules": "firewall_rules",
  "NAT rules": "nat_rules",
  Aliases: "aliases",
  Schedules: "schedules",
  "DHCP servers": "dhcp_servers",
  "DHCP relay": "dhcp_relays",
  DNS: "dns",
  "NTP server": "ntpd",
  SNMP: "snmpd",
  "Remote syslog": "syslog",
  "Traffic shaper queues": "shaper_queues",
  "Limiter pipes": "dnshaper_pipes",
  "Load balancer": "lb_pools",
  "Captive portal": "captive_portal_zones",
  "Dynamic DNS": "dyndns_entries",
  "IGMP proxy": "igmpproxy_entries",
  "Router Advertisements (IPv6)": "radvd_interfaces",
  "UPS monitoring": "ups",
  "Captive-portal vouchers": "voucher_rolls",
  "FTP proxy": "ftpproxy",
  "OpenVPN servers": "openvpn_servers",
  "OpenVPN clients": "openvpn_clients",
  "OpenVPN client-specific overrides": "openvpn_cscs",
  "IPsec — phase 1": "ipsec_phase1",
  "IPsec — phase 2": "ipsec_phase2",
  "IPsec — pre-shared keys": "ipsec_psks",
  "Certificate authorities": "certificate_authorities",
  Certificates: "certificates",
  "Certificate revocation lists": "crls",
  Users: "users",
  Groups: "groups",
  "External auth servers": "authservers",
  "Installed packages": "installedpackages",
};

/** Section shim over Card — existing call sites keep using `<Section>` so
 *  the rewrite stays minimal. The group color is inferred from the
 *  title via ``TITLE_TO_KEY``. Unmarked (``muted``) sections keep a
 *  neutral stripe — used for the "Other sections (raw XML)" fallback. */
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
  const group: SectionGroup = muted
    ? "neutral"
    : sectionGroup(TITLE_TO_KEY[title] ?? "");
  return (
    <Card title={title} group={group} count={count} id={sectionId(title)}>
      {children}
    </Card>
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
  if (cfg.laggs.length) entries.push(["LAGG", cfg.laggs.length]);
  if (cfg.wol.length) entries.push(["Wake-on-LAN", cfg.wol.length]);
  if (cfg.virtual_ips.length)
    entries.push(["Virtual IPs / CARP", cfg.virtual_ips.length]);
  if (cfg.hasync) entries.push(["HA / CARP sync", 1]);
  if (cfg.gateways.length) entries.push(["Gateways", cfg.gateways.length]);
  if (cfg.gateway_groups.length)
    entries.push(["Gateway groups", cfg.gateway_groups.length]);
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
  if (cfg.dyndns_entries.length)
    entries.push(["Dynamic DNS", cfg.dyndns_entries.length]);
  if (cfg.igmpproxy_entries.length)
    entries.push(["IGMP proxy", cfg.igmpproxy_entries.length]);
  if (cfg.radvd_interfaces.length)
    entries.push([
      "Router Advertisements (IPv6)",
      cfg.radvd_interfaces.length,
    ]);
  if (cfg.notifications) entries.push(["Notifications", 1]);
  if (cfg.ups) entries.push(["UPS monitoring", 1]);
  if (cfg.voucher_rolls.length)
    entries.push(["Captive-portal vouchers", cfg.voucher_rolls.length]);
  if (cfg.ftpproxy) entries.push(["FTP proxy", 1]);
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
  if (cfg.crls.length)
    entries.push(["Certificate revocation lists", cfg.crls.length]);
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
      className="inline-flex items-center gap-1 rounded border border-[hsl(var(--group-vpn))]/30 bg-[hsl(var(--group-vpn))]/10 px-1.5 py-0.5 font-mono text-[11px] text-[hsl(var(--group-vpn))]"
    >
      <Lock aria-hidden="true" className="h-3 w-3" /> redacted
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
  rowKeys,
}: {
  headers: string[];
  rows: React.ReactNode[][];
  /** Stable per-row keys. When omitted, falls back to index which is
   *  fine for non-reordering tables. Firewall / NAT tables pass
   *  rule trackers so reordering diffs don't confuse React. */
  rowKeys?: (string | number)[];
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
            <tr
              key={rowKeys?.[i] ?? i}
              className="border-b border-border/50 last:border-0"
            >
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
      headers={["Name", "Device", "Enabled", "IPv4", "IPv6", "Description"]}
      rows={rows.map((r) => [
        <InterfaceChip key="k" name={r.key} />,
        <span key="i" className="font-mono text-xs">
          {r.if_ ?? "—"}
        </span>,
        <StatusPill key="e" enabled={r.enabled} />,
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
      rowKeys={rows.map((r) => r.name)}
      rows={rows.map((r) => [
        r.name,
        <InterfaceChip key="i" name={r.interface} />,
        <span key="g" className="font-mono text-xs">
          {r.gateway ?? "—"}
        </span>,
        r.monitor ?? "—",
        r.defaultgw ? <Badge tone="success">default</Badge> : "",
        r.descr ?? "—",
      ])}
    />
  );
}

function GatewayGroupsTable({ rows }: { rows: GatewayGroup[] }) {
  return (
    <Table
      headers={["Name", "Trigger", "Members", "Description"]}
      rowKeys={rows.map((r) => r.name)}
      rows={rows.map((r) => [
        r.name,
        r.trigger ?? "—",
        <span key="m" className="font-mono text-xs">
          {r.members.length ? r.members.join(", ") : "—"}
        </span>,
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
      // r.key is ``tracker:{id}`` when the rule has a tracker, else a
      // content hash — unique per-rule in both branches. Using it
      // directly preserves React identity across reorders (which was
      // the whole point of rowKeys; a positional suffix would defeat it).
      rowKeys={rows.map((r) => r.key)}
      rows={rows.map((r, i) => [
        <span key="n" className="font-mono text-xs text-muted-fg">
          {i + 1}
        </span>,
        <ActionPill key="a" type={r.type} />,
        <InterfaceChip key="i" name={r.interface} />,
        <span key="p" className="font-mono text-xs">
          {r.protocol ?? "any"}
        </span>,
        <span key="s" className="font-mono text-xs">
          {endpointStr(r.source)}
        </span>,
        <span key="dst" className="font-mono text-xs">
          {endpointStr(r.destination)}
        </span>,
        <span key="d" className="flex items-center gap-1">
          {r.descr ?? "—"}
          {r.disabled && <Badge tone="muted">disabled</Badge>}
          {r.log && <Badge tone="warn">log</Badge>}
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
      rowKeys={rows.map((r) => r.key)}
      rows={rows.map((r) => [
        <Badge
          key="k"
          tone={
            r.kind === "port_forward"
              ? "warn"
              : r.kind === "one_to_one"
                ? "success"
                : "muted"
          }
          className="font-mono text-[10px] uppercase"
        >
          {r.kind.replace("_", " ")}
        </Badge>,
        <InterfaceChip key="i" name={r.interface} />,
        <span key="p" className="font-mono text-xs">
          {r.protocol ?? "—"}
        </span>,
        <span key="s" className="font-mono text-xs">
          {endpointStr(r.source)}
        </span>,
        <span key="dst" className="font-mono text-xs">
          {endpointStr(r.destination)}
        </span>,
        <span key="t" className="font-mono text-xs">
          {r.target ?? "—"}
        </span>,
        r.local_port ?? "—",
        <span key="d" className="flex items-center gap-1">
          {r.descr ?? "—"}
          {r.disabled && <Badge tone="muted">disabled</Badge>}
        </span>,
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
        <span key="p" className="font-mono text-xs">
          {v.if_ ?? "—"}
        </span>,
        <span key="t" className="font-mono">
          {v.tag ?? "—"}
        </span>,
        v.pcp ?? "—",
        <span key="d" className="font-mono text-xs">
          {v.vlanif ?? "—"}
        </span>,
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
        <span key="bi" className="font-mono">
          {b.bridgeif}
        </span>,
        <span key="m" className="flex flex-wrap gap-1">
          {b.members.length > 0
            ? b.members.map((m) => <InterfaceChip key={m} name={m} />)
            : "—"}
        </span>,
        <StatusPill key="s" enabled={b.enablestp} labels={{ on: "on", off: "off" }} />,
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
      rows={rows.map((w) => [
        <span key="m" className="font-mono">
          {w.mac}
        </span>,
        <InterfaceChip key="i" name={w.interface} />,
        w.descr ?? "—",
      ])}
    />
  );
}

function VirtualIpsTable({ rows }: { rows: VirtualIP[] }) {
  return (
    <Table
      headers={["Mode", "Interface", "Subnet", "VHID", "CARP pwd", "Description"]}
      rows={rows.map((v) => [
        <Badge
          key="m"
          tone={v.mode === "carp" ? "warn" : "muted"}
          className="uppercase"
        >
          {v.mode ?? "—"}
        </Badge>,
        <InterfaceChip key="i" name={v.interface} />,
        <span key="s" className="font-mono text-xs">
          {v.subnet
            ? `${v.subnet}${v.subnet_bits ? "/" + v.subnet_bits : ""}`
            : "—"}
        </span>,
        <span key="vh" className="font-mono">
          {v.vhid ?? "—"}
        </span>,
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
        ["Trap community", <RV v={s.trapstring} key="ts" />],
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
        <RV v={z.radius_secret} key="rs" />,
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
  if (ip.squid) n += 1;
  if (ip.freeradius) n += 1;
  if (ip.telegraf) n += 1;
  if (ip.frr) n += 1;
  if (ip.zabbix) n += 1;
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
      {ip.squid && <SquidPanel p={ip.squid} />}
      {ip.freeradius && <FreeRadiusPanel p={ip.freeradius} />}
      {ip.telegraf && <TelegrafPanel p={ip.telegraf} />}
      {ip.frr && <FrrPanel p={ip.frr} />}
      {ip.zabbix && <ZabbixPanel p={ip.zabbix} />}
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

// ---------- v0.12.0: shared chips + semantic coloring ---------------------

/** Colored interface-key chip. Same key always gets the same color
 *  (hashed via ``interfaceChipClasses``) so operators can spot
 *  "this rule is on LAN" from across the table without reading text.
 *
 *  Uses a border-only treatment (no background fill) so the chip's
 *  color vocabulary doesn't collide with action semantics — a green
 *  "pass" badge sitting next to a green-striped LAN interface chip
 *  would be ambiguous in a firewall-rule row. Border-only keeps
 *  identity recognition but downgrades visual weight below the
 *  action pill.
 *
 *  Memoized because it's rendered hundreds of times per firewall
 *  view and interfaceChipClasses runs a djb2 hash per render.
 */
export const InterfaceChip = memo(function InterfaceChip({
  name,
  className,
}: {
  name: string | null | undefined;
  className?: string;
}) {
  if (!name) return <span className="text-muted-fg">—</span>;
  const c = interfaceChipClasses(name);
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 text-[11px] font-medium bg-bg",
        c.fg,
        c.border,
        className,
      )}
    >
      {interfaceLabel(name)}
    </span>
  );
});

/** Colored pill for firewall-rule action type. */
function ActionPill({ type }: { type: string | null | undefined }) {
  if (!type) return <span className="text-muted-fg">—</span>;
  const t = type.toLowerCase();
  let tone: "success" | "danger" | "warn" | "muted" = "muted";
  if (t === "pass" || t === "allow") tone = "success";
  else if (t === "block" || t === "reject") tone = "danger";
  else if (t === "match") tone = "warn";
  return (
    <Badge tone={tone} className="uppercase">
      {type}
    </Badge>
  );
}

/** "enabled" → green, "disabled" / false → muted gray. */
function StatusPill({
  enabled,
  labels,
}: {
  enabled: boolean;
  labels?: { on: string; off: string };
}) {
  const on = labels?.on ?? "enabled";
  const off = labels?.off ?? "disabled";
  return (
    <Badge tone={enabled ? "success" : "muted"}>
      {enabled ? on : off}
    </Badge>
  );
}

// ---------- v0.12.0: new section renderers --------------------------------

function LaggsTable({ rows }: { rows: Lagg[] }) {
  return (
    <Table
      headers={["Device", "Members", "Protocol", "LACP timeout", "Description"]}
      rows={rows.map((la) => [
        <span key="d" className="font-mono">
          {la.laggif}
        </span>,
        <span key="m" className="flex flex-wrap gap-1">
          {la.members.map((m) => (
            <InterfaceChip key={m} name={m} />
          ))}
        </span>,
        la.proto ?? "—",
        la.lacptimeout ? `${la.lacptimeout}${la.lacp_fast_timeout ? " (fast)" : ""}` : "—",
        la.descr ?? "—",
      ])}
    />
  );
}

function DyndnsTable({ rows }: { rows: DyndnsEntry[] }) {
  return (
    <Table
      headers={[
        "Provider",
        "Host",
        "Interface",
        "Enabled",
        "Token / PW",
        "Description",
      ]}
      rowKeys={rows.map((d) => d.key)}
      rows={rows.map((d) => [
        <span key="p" className="font-mono text-xs">
          {d.type ?? "—"}
        </span>,
        d.host ?? d.domainname ?? "—",
        <InterfaceChip key="i" name={d.interface} />,
        <StatusPill key="e" enabled={d.enabled} />,
        // Either <password> or <token> may carry the secret depending
        // on provider; show a single Redacted chip when either is set.
        d.token === "***redacted***" || d.password === "***redacted***" ? (
          <Redacted key="r" />
        ) : (
          "—"
        ),
        d.descr ?? "—",
      ])}
    />
  );
}

function IgmpProxyTable({ rows }: { rows: IgmpProxyEntry[] }) {
  return (
    <Table
      headers={["Role", "Interface", "Networks", "Description"]}
      rows={rows.map((i) => [
        <Badge
          key="t"
          tone={i.type === "upstream" ? "warn" : "muted"}
          className="uppercase"
        >
          {i.type ?? "?"}
        </Badge>,
        <InterfaceChip key="i" name={i.ifname} />,
        <span key="n" className="font-mono text-xs">
          {i.networks.join(", ") || "—"}
        </span>,
        i.descr ?? "—",
      ])}
    />
  );
}

function RadvdTable({ rows }: { rows: RadvdInterfaceConfig[] }) {
  return (
    <Table
      headers={[
        "Interface",
        "Mode",
        "Priority",
        "Lifetime",
        "DNS",
        "Domain search",
      ]}
      rows={rows.map((r) => [
        <InterfaceChip key="i" name={r.interface} />,
        <Badge
          key="m"
          tone={r.ramode === "disabled" ? "muted" : "success"}
          className="uppercase"
        >
          {r.ramode ?? "?"}
        </Badge>,
        r.rapriority ?? "—",
        r.ralifetime ?? "—",
        <span key="dns" className="font-mono text-xs">
          {r.radns.join(", ") || "—"}
        </span>,
        r.radomainsearchlist ?? "—",
      ])}
    />
  );
}

function NotificationsPanel({ n }: { n: NotificationConfig }) {
  const channels: { label: string; enabled: boolean; detail: string; secret: boolean }[] = [];
  if (n.smtp) {
    channels.push({
      label: "SMTP",
      enabled: n.smtp.enabled,
      detail: n.smtp.ipaddress
        ? `${n.smtp.ipaddress}:${n.smtp.port ?? "?"}${n.smtp.ssl ? " (TLS)" : ""}`
        : "not configured",
      secret: n.smtp.password === "***redacted***",
    });
  }
  if (n.pushover) {
    channels.push({
      label: "Pushover",
      enabled: n.pushover.enabled,
      detail: "API",
      secret:
        n.pushover.api_key === "***redacted***" ||
        n.pushover.user_key === "***redacted***",
    });
  }
  if (n.slack) {
    channels.push({
      label: "Slack",
      enabled: n.slack.enabled,
      detail: "webhook",
      secret: n.slack.webhook_url === "***redacted***",
    });
  }
  if (n.telegram) {
    channels.push({
      label: "Telegram",
      enabled: n.telegram.enabled,
      detail: `chat ${n.telegram.chat_id ?? "?"}`,
      secret: n.telegram.api_token === "***redacted***",
    });
  }
  if (n.growl) {
    channels.push({
      label: "Growl",
      enabled: n.growl.enabled,
      detail: n.growl.ipaddress ?? "?",
      secret: n.growl.password === "***redacted***",
    });
  }
  return (
    <Table
      headers={["Channel", "Enabled", "Detail", "Credential"]}
      rows={channels.map((c) => [
        c.label,
        <StatusPill key="e" enabled={c.enabled} />,
        <span key="d" className="text-muted-fg">
          {c.detail}
        </span>,
        c.secret ? <Redacted /> : "—",
      ])}
    />
  );
}

function UpsPanel({ u }: { u: UpsConfig }) {
  return (
    <Dl
      items={[
        ["Enabled", <StatusPill key="e" enabled={u.enable} />],
        ["Driver", u.driver ?? "—"],
        ["Port", u.port ?? "—"],
        ["UPS name", u.upsname ?? "—"],
        ["Cable", u.cable ?? "—"],
        ["Remote user", u.remoteuser ?? "—"],
        [
          "Remote password",
          u.remotepassword === "***redacted***" ? <Redacted /> : "—",
        ],
      ]}
    />
  );
}

function VoucherTable({ rows }: { rows: VoucherRoll[] }) {
  return (
    <Table
      headers={["Roll #", "Minutes / code", "Remaining", "Description"]}
      rows={rows.map((v) => [
        <span key="n" className="font-mono">
          {v.number}
        </span>,
        v.minutes ?? "—",
        v.count ?? "—",
        v.descr ?? "—",
      ])}
    />
  );
}

function FtpProxyPanel({ f }: { f: FtpProxyConfig }) {
  return (
    <Dl
      items={[
        ["Enabled", <StatusPill key="e" enabled={f.enable} />],
        ["Ports", f.ports ?? "—"],
        ["Interface", <InterfaceChip key="i" name={f.interface} />],
      ]}
    />
  );
}

function CrlTable({ rows }: { rows: CertificateRevocationList[] }) {
  return (
    <Table
      headers={["Description", "Method", "CA ref", "Revoked certs"]}
      rows={rows.map((c) => [
        c.descr ?? "—",
        c.method ?? "—",
        <span key="ca" className="font-mono text-xs">
          {c.caref ?? "—"}
        </span>,
        <Badge
          key="rc"
          tone={c.revoked_cert_refids.length ? "danger" : "muted"}
          className="font-mono"
        >
          {c.revoked_cert_refids.length}
        </Badge>,
      ])}
    />
  );
}

// ---------- v0.12.0: new package renderers --------------------------------

function SquidPanel({ p }: { p: SquidBundle }) {
  return (
    <PackageCard title="Squid / squidGuard">
      {p.squid && (
        <div className="mb-2">
          <div className="mb-1 text-xs uppercase text-muted-fg">Proxy</div>
          <Dl
            items={[
              ["Enabled", <StatusPill key="e" enabled={p.squid.enable} />],
              [
                "Listen",
                p.squid.active_interface
                  ? `${p.squid.active_interface}:${p.squid.proxy_port ?? "3128"}`
                  : "—",
              ],
              [
                "Transparent",
                <StatusPill
                  key="t"
                  enabled={p.squid.transparent_mode}
                  labels={{ on: "yes", off: "no" }}
                />,
              ],
              [
                "Allowed interfaces",
                <span key="ai" className="flex flex-wrap gap-1">
                  {p.squid.allow_interface.map((i) => (
                    <InterfaceChip key={i} name={i} />
                  ))}
                </span>,
              ],
              ["Auth method", p.squid.auth_method ?? "none"],
              ["LDAP server", p.squid.ldap_server ?? "—"],
              [
                "LDAP bind password",
                p.squid.ldap_bindpw === "***redacted***" ? (
                  <Redacted />
                ) : (
                  "—"
                ),
              ],
              [
                "NTLM admin password",
                p.squid.ntlm_admin_password === "***redacted***" ? (
                  <Redacted />
                ) : (
                  "—"
                ),
              ],
            ]}
          />
        </div>
      )}
      {p.squidguard && (
        <div>
          <div className="mb-1 text-xs uppercase text-muted-fg">
            squidGuard
          </div>
          <Dl
            items={[
              [
                "Enabled",
                <StatusPill key="e" enabled={p.squidguard.enabled} />,
              ],
              [
                "Blacklist",
                p.squidguard.blacklist_enabled
                  ? p.squidguard.blacklist_url ?? "enabled"
                  : "disabled",
              ],
              ["Targets", `${p.squidguard.targets.length}`],
              ["ACLs", `${p.squidguard.acls.length}`],
            ]}
          />
        </div>
      )}
    </PackageCard>
  );
}

function FreeRadiusPanel({ p }: { p: FreeRadiusConfig }) {
  return (
    <PackageCard title="FreeRADIUS">
      <Dl
        items={[
          ["Enabled", <StatusPill key="e" enabled={p.enabled} />],
          ["Interfaces", `${p.interfaces.length}`],
          ["Clients", `${p.clients.length}`],
          ["Users", `${p.users.length}`],
        ]}
      />
      {p.clients.length > 0 && (
        <div className="mt-2">
          <div className="mb-1 text-xs uppercase text-muted-fg">Clients (NAS)</div>
          <Table
            headers={["Name", "IP", "NAS type", "Shared secret", "Description"]}
            rows={p.clients.map((c) => [
              c.name,
              c.ipaddr ?? "—",
              c.nas_type ?? "—",
              c.shared_secret === "***redacted***" ? <Redacted /> : "—",
              c.descr ?? "—",
            ])}
          />
        </div>
      )}
      {p.users.length > 0 && (
        <div className="mt-2">
          <div className="mb-1 text-xs uppercase text-muted-fg">Users</div>
          <Table
            headers={["Name", "Auth type", "Password", "Expires"]}
            rows={p.users.map((u) => [
              u.name,
              u.auth_type ?? "—",
              u.password === "***redacted***" ? <Redacted /> : "—",
              u.expiration ?? "—",
            ])}
          />
        </div>
      )}
    </PackageCard>
  );
}

function TelegrafPanel({ p }: { p: TelegrafConfig }) {
  return (
    <PackageCard title="Telegraf">
      <Dl
        items={[
          ["Enabled", <StatusPill key="e" enabled={p.enabled} />],
          ["Interval", p.interval ?? "—"],
          ["Output", p.output_plugin ?? "—"],
          ["URL", p.url ?? "—"],
          ["Database / bucket", p.bucket ?? p.database ?? "—"],
          ["Organization", p.organization ?? "—"],
          ["Username", p.username ?? "—"],
          [
            "Credential",
            p.token === "***redacted***" ? <Redacted /> :
              p.password === "***redacted***" ? <Redacted /> : "—",
          ],
        ]}
      />
    </PackageCard>
  );
}

function FrrPanel({ p }: { p: FrrConfig }) {
  return (
    <PackageCard title="FRR (routing daemon)">
      <Dl
        items={[
          ["Enabled", <StatusPill key="e" enabled={p.enabled} />],
        ]}
      />
      {p.bgp && (
        <div className="mt-2">
          <div className="mb-1 text-xs uppercase text-muted-fg">BGP</div>
          <Dl
            items={[
              [
                "Enabled",
                <StatusPill key="e" enabled={p.bgp.enabled} />,
              ],
              ["Local AS", p.bgp.local_as ?? "—"],
              ["Router id", p.bgp.router_id ?? "—"],
            ]}
          />
          {p.bgp.neighbors.length > 0 && (
            <Table
              headers={["Peer", "Address", "Remote AS", "MD5 password"]}
              rows={p.bgp.neighbors.map((n) => [
                n.name,
                n.peer_address ?? "—",
                n.remote_as ?? "—",
                n.password === "***redacted***" ? <Redacted /> : "—",
              ])}
            />
          )}
        </div>
      )}
      {p.ospf && (
        <div className="mt-2">
          <div className="mb-1 text-xs uppercase text-muted-fg">OSPF</div>
          <Dl
            items={[
              [
                "Enabled",
                <StatusPill key="e" enabled={p.ospf.enabled} />,
              ],
              ["Router id", p.ospf.router_id ?? "—"],
            ]}
          />
          {p.ospf.interfaces.length > 0 && (
            <Table
              headers={[
                "Interface",
                "Area",
                "Cost",
                "Hello / Dead",
                "MD5",
              ]}
              rows={p.ospf.interfaces.map((i) => [
                <InterfaceChip key="i" name={i.interface} />,
                i.area ?? "—",
                i.cost ?? "—",
                `${i.hello_interval ?? "?"} / ${i.dead_interval ?? "?"}`,
                i.md5_password === "***redacted***" ? <Redacted /> : "—",
              ])}
            />
          )}
        </div>
      )}
    </PackageCard>
  );
}

function ZabbixPanel({ p }: { p: ZabbixBundle }) {
  return (
    <PackageCard title="Zabbix">
      {p.agent && (
        <div className="mb-2">
          <div className="mb-1 text-xs uppercase text-muted-fg">Agent</div>
          <Dl
            items={[
              [
                "Enabled",
                <StatusPill key="e" enabled={p.agent.enabled} />,
              ],
              ["Server", p.agent.server ?? "—"],
              ["Server (active)", p.agent.serveractive ?? "—"],
              ["Hostname", p.agent.hostname ?? "—"],
              ["Listen port", p.agent.listenport ?? "—"],
              ["PSK identity", p.agent.tls_psk_identity ?? "—"],
              [
                "PSK",
                p.agent.tls_psk === "***redacted***" ? (
                  <Redacted />
                ) : (
                  "—"
                ),
              ],
            ]}
          />
        </div>
      )}
      {p.proxy && (
        <div>
          <div className="mb-1 text-xs uppercase text-muted-fg">Proxy</div>
          <Dl
            items={[
              [
                "Enabled",
                <StatusPill key="e" enabled={p.proxy.enabled} />,
              ],
              ["Server", p.proxy.server ?? "—"],
              ["Hostname", p.proxy.hostname ?? "—"],
              [
                "PSK",
                p.proxy.tls_psk === "***redacted***" ? (
                  <Redacted />
                ) : (
                  "—"
                ),
              ],
            ]}
          />
        </div>
      )}
    </PackageCard>
  );
}
