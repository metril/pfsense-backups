import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Check, Copy } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import {
  ActionPill,
  Dl,
  PackageCard,
  Redacted,
  RV,
  StatusPill,
  Table,
} from "@/components/view/primitives";
import { ExpandCollapseAll } from "@/components/ui/ExpandCollapseAll";
import { FilterBar } from "@/components/ui/FilterBar";
import { FilterProvider } from "@/components/ui/FilterContext";
import { FilterHiddenAnchorBanner } from "@/components/ui/FilterHiddenAnchorBanner";
import { Xref, XrefList } from "@/components/ui/Xref";
import { CardGroupProvider } from "@/components/CardGroupContext";
import { XrefProvider } from "@/components/xref/XrefContext";
import { DeepLinkBridge } from "@/components/xref/DeepLinkBridge";
import { QuickJump } from "@/components/xref/QuickJump";
import { itemId, rowAnchorId } from "@/lib/xref";
import {
  buildMatcher,
  rowHaystack,
  type FilterMatcher,
} from "@/lib/filter";
import { useMediaQuery } from "@/lib/useMediaQuery";
import { useActiveSection } from "@/lib/useActiveSection";
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
  Endpoint,
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
  // v0.17.0 — additional package parsers
  AvahiConfig,
  MiniUpnpdConfig,
  OpenvpnClientExportConfig,
  ShellCmdSettings,
  SnortConfig,
  WireGuardConfig,
  // v0.14.0
  ApiKeyEntry,
  DiagPreferences,
  EzShaperConfig,
  InterfaceGroup,
  L2tpConfig,
  OvpnServerWizard,
  PppoeServerEntry,
  ProxyArpEntry,
  SshData,
  SshHostKeyFile,
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
  const { data: rawData, error, isLoading } = useParsedBackup(backupId);
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
  // Pre-filter tabular arrays up front — the existing ``length > 0``
  // conditionals downstream handle hiding sections automatically. This
  // keeps the render tree untouched (just replaces ``data`` with a
  // narrowed version when the filter is active).
  const data = useMemo<ParsedConfig | null>(() => {
    if (!rawData) return null;
    if (!matcher.active) return rawData;
    return narrowConfig(rawData, matcher);
  }, [rawData, matcher]);
  const showTitle = useCallback(
    (title: string) => !matcher.active || matcher.match(title),
    [matcher],
  );
  const sectionCounter = useMemo(
    () =>
      data && rawData
        ? {
            visible: countVisibleSections(data, matcher),
            total: countVisibleSections(rawData, buildMatcher("")),
          }
        : undefined,
    [data, rawData, matcher],
  );

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
    // Xref index builds from the UNFILTERED config so chips resolve even
    // when the referenced row is currently filtered out (e.g. a firewall
    // rule pointing at alias ``RFC1918`` while the user has filtered on
    // ``"LAN"``). Using the narrowed ``data`` would produce dead chips.
    <XrefProvider data={rawData!}>
    <FilterProvider query={filterQuery}>
    <CardGroupProvider scope={`view:${backupId}`}>
    <DeepLinkBridge includeHashchange />
    <ViewerLayout
      cfg={data}
      filterQuery={filterQuery}
      setFilterQuery={setFilterQuery}
      sectionCounter={sectionCounter}
    >
        <div className="mt-4 space-y-3">
        {data.system && showTitle("System") && (
          <Section title="System" count={1}>
            <SystemPanel s={data.system} />
          </Section>
        )}
        {data.revision && showTitle("Last revision") && (
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
        {data.lastchange && showTitle("Last change") && (
          <Section title="Last change" count={1}>
            <Dl
              items={[
                ["Time (epoch)", data.lastchange.time ?? "—"],
                ["By", data.lastchange.username ?? "—"],
              ]}
            />
          </Section>
        )}
        {data.theme && showTitle("Theme") && (
          <Section title="Theme" count={1}>
            <Dl items={[["webGUI theme", data.theme.name ?? "—"]]} />
          </Section>
        )}
        {data.diag && showTitle("Diagnostic preferences") && (
          <Section title="Diagnostic preferences" count={1}>
            <DiagPanel s={data.diag} />
          </Section>
        )}
        {data.sshdata && showTitle("SSH host keys") && (
          <Section title="SSH host keys" count={1}>
            <SshDataPanel s={data.sshdata} />
          </Section>
        )}
        {data.apikeys.length > 0 && (
          <Section title="API keys" count={data.apikeys.length}>
            <ApiKeysTable rows={data.apikeys} />
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
        {data.legacy_bridge && showTitle("Bridge (legacy)") && (
          <Section title="Bridge (legacy)" count={1}>
            <Dl
              items={[
                ["Enabled", data.legacy_bridge.enabled ? "yes" : "no"],
                [
                  "Members",
                  <span key="m" className="inline-flex flex-wrap gap-1">
                    {data.legacy_bridge.interfaces.length
                      ? data.legacy_bridge.interfaces.map((m) => (
                          <InterfaceChip key={m} name={m} />
                        ))
                      : "—"}
                  </span>,
                ],
              ]}
            />
          </Section>
        )}
        {data.interface_groups.length > 0 && (
          <Section
            title="Interface groups"
            count={data.interface_groups.length}
          >
            <InterfaceGroupsTable rows={data.interface_groups} />
          </Section>
        )}
        {data.proxyarp.length > 0 && (
          <Section title="Proxy ARP" count={data.proxyarp.length}>
            <ProxyArpTable rows={data.proxyarp} />
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
        {data.hasync && showTitle("HA / CARP sync") && (
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
        {data.dns && showTitle("DNS") && (
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
        {data.notifications && showTitle("Notifications") && (
          <Section title="Notifications" count={1}>
            <NotificationsPanel n={data.notifications} />
          </Section>
        )}
        {data.ups && showTitle("UPS monitoring") && (
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
        {data.ftpproxy && showTitle("FTP proxy") && (
          <Section title="FTP proxy" count={1}>
            <FtpProxyPanel f={data.ftpproxy} />
          </Section>
        )}
        {data.ntpd && showTitle("NTP server") && (
          <Section title="NTP server" count={1}>
            <NtpdPanel n={data.ntpd} />
          </Section>
        )}
        {data.snmpd && showTitle("SNMP") && (
          <Section title="SNMP" count={1}>
            <SnmpdPanel s={data.snmpd} />
          </Section>
        )}
        {data.syslog && showTitle("Remote syslog") && (
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
        {data.ovpnserver_wizard && showTitle("OpenVPN server (wizard state)") && (
          <Section title="OpenVPN server (wizard state)" count={1}>
            <OvpnServerWizardPanel w={data.ovpnserver_wizard} />
          </Section>
        )}
        {data.l2tp && showTitle("L2TP server") && (
          <Section title="L2TP server" count={1}>
            <L2tpPanel c={data.l2tp} />
          </Section>
        )}
        {data.pppoe_servers.length > 0 && (
          <Section
            title="PPPoE servers"
            count={data.pppoe_servers.length}
          >
            <PppoeServersTable rows={data.pppoe_servers} />
          </Section>
        )}
        {data.ezshaper && showTitle("Shaper wizard state") && (
          <Section title="Shaper wizard state" count={1}>
            <EzShaperPanel c={data.ezshaper} />
          </Section>
        )}
        {data.dhcp_backend && showTitle("DHCP backend") && (
          <Section title="DHCP backend" count={1}>
            <Dl
              items={[["Backend", data.dhcp_backend.backend ?? "—"]]}
            />
          </Section>
        )}
        {data.installedpackages && showTitle("Installed packages") && (
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
    </ViewerLayout>
    </CardGroupProvider>
    </FilterProvider>
    </XrefProvider>
  );
}

/** Two-up wrapper: at ≥1700px renders the filter + ToC as a sticky
 *  left sidebar with scrollable main content on the right; below
 *  that, falls back to the v0.14 horizontal chip strip + full-width
 *  content. The 1700px crossover is the point at which sidebar-
 *  mode content (viewport − 15rem sidebar − 1.5rem gap − 2rem
 *  padding = V − 296) first equals narrow-mode content (capped at
 *  1400px via ``max-w-[1400px]`` below). V − 296 ≥ 1400 → V ≥ 1696,
 *  rounded up to 1700. If the sidebar width or the narrow cap ever
 *  moves, the breakpoint has to move with them. Layout only — no
 *  section-rendering logic lives here. */
function ViewerLayout({
  cfg,
  filterQuery,
  setFilterQuery,
  sectionCounter,
  children,
}: {
  cfg: ParsedConfig;
  filterQuery: string;
  setFilterQuery: (next: string) => void;
  sectionCounter?: { visible: number; total: number };
  children: React.ReactNode;
}) {
  const isWide = useMediaQuery("(min-width: 1700px)");
  // IntersectionObserver only runs when the sidebar is rendered —
  // no point paying for it in narrow mode where nothing consumes
  // the active id. Passing ``filterQuery`` as the version rebuilds
  // the observer whenever the filter changes (not just when the
  // visible count changes), so two filters that happen to leave
  // the same number of sections visible still refresh the observed
  // set correctly.
  const activeId = useActiveSection(
    isWide ? "section-" : null,
    filterQuery,
  );

  if (isWide) {
    return (
      <div className="h-full overflow-auto p-4">
        <QuickJump />
        <div className="mx-auto grid max-w-[1920px] grid-cols-[15rem_1fr] gap-6">
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
            <TableOfContents cfg={cfg} orientation="vertical" activeId={activeId} />
          </aside>
          <div className="min-w-0">
            <FilterHiddenAnchorBanner onClear={() => setFilterQuery("")} />
            {children}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto p-4">
      <QuickJump />
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
        <TableOfContents cfg={cfg} />
        {children}
      </div>
    </div>
  );
}

/** Returns a ``ParsedConfig`` with every tabular array narrowed to
 *  rows that match the filter (or left untouched when the section
 *  title itself matches — so typing a section name keeps every row in
 *  it). Single-entity fields (system, dns, etc.) are passed through
 *  unchanged; the render tree gates those via ``shouldShowTitle``. */
function narrowConfig(cfg: ParsedConfig, filter: FilterMatcher): ParsedConfig {
  const narrow = <T,>(title: string, arr: T[]): T[] => {
    if (filter.match(title)) return arr;
    return arr.filter((r) => filter.match(rowHaystack(r)));
  };
  return {
    ...cfg,
    interfaces: narrow("Interfaces", cfg.interfaces),
    vlans: narrow("VLANs", cfg.vlans),
    bridges: narrow("Bridges", cfg.bridges),
    gifs: narrow("GIF tunnels", cfg.gifs),
    gres: narrow("GRE tunnels", cfg.gres),
    ppps: narrow("PPP interfaces", cfg.ppps),
    qinqs: narrow("QinQ", cfg.qinqs),
    laggs: narrow("LAGG", cfg.laggs),
    wol: narrow("Wake-on-LAN", cfg.wol),
    virtual_ips: narrow("Virtual IPs / CARP", cfg.virtual_ips),
    gateways: narrow("Gateways", cfg.gateways),
    gateway_groups: narrow("Gateway groups", cfg.gateway_groups),
    static_routes: narrow("Static routes", cfg.static_routes),
    firewall_rules: narrow("Firewall rules", cfg.firewall_rules),
    nat_rules: narrow("NAT rules", cfg.nat_rules),
    aliases: narrow("Aliases", cfg.aliases),
    schedules: narrow("Schedules", cfg.schedules),
    dhcp_servers: narrow("DHCP servers", cfg.dhcp_servers),
    dhcp_relays: narrow("DHCP relay", cfg.dhcp_relays),
    dyndns_entries: narrow("Dynamic DNS", cfg.dyndns_entries),
    igmpproxy_entries: narrow("IGMP proxy", cfg.igmpproxy_entries),
    radvd_interfaces: narrow(
      "Router Advertisements (IPv6)",
      cfg.radvd_interfaces,
    ),
    voucher_rolls: narrow("Captive-portal vouchers", cfg.voucher_rolls),
    shaper_queues: narrow("Traffic shaper queues", cfg.shaper_queues),
    dnshaper_pipes: narrow("Limiter pipes", cfg.dnshaper_pipes),
    lb_pools: narrow("Load balancer", cfg.lb_pools),
    lb_virtual_servers: narrow("Load balancer", cfg.lb_virtual_servers),
    captive_portal_zones: narrow("Captive portal", cfg.captive_portal_zones),
    openvpn_servers: narrow("OpenVPN servers", cfg.openvpn_servers),
    openvpn_clients: narrow("OpenVPN clients", cfg.openvpn_clients),
    openvpn_cscs: narrow(
      "OpenVPN client-specific overrides",
      cfg.openvpn_cscs,
    ),
    ipsec_phase1: narrow("IPsec phase 1", cfg.ipsec_phase1),
    ipsec_phase2: narrow("IPsec phase 2", cfg.ipsec_phase2),
    ipsec_psks: narrow("IPsec pre-shared keys", cfg.ipsec_psks),
    certificate_authorities: narrow(
      "Certificate authorities",
      cfg.certificate_authorities,
    ),
    certificates: narrow("Certificates", cfg.certificates),
    crls: narrow("Certificate revocation lists", cfg.crls),
    users: narrow("Users", cfg.users),
    groups: narrow("Groups", cfg.groups),
    authservers: narrow("External auth servers", cfg.authservers),
    sysctl: narrow("Sysctl tunables", cfg.sysctl),
    cron: narrow("Cron jobs", cfg.cron),
    apikeys: narrow("API keys", cfg.apikeys),
    interface_groups: narrow("Interface groups", cfg.interface_groups),
    proxyarp: narrow("Proxy ARP", cfg.proxyarp),
    pppoe_servers: narrow("PPPoE servers", cfg.pppoe_servers),
    unrecognized_sections: narrow(
      "Other sections (raw XML)",
      cfg.unrecognized_sections,
    ),
  };
}

/** Counts sections that would render in ``data`` given the current
 *  filter. Used to feed the "N of M sections" counter in the FilterBar. */
function countVisibleSections(
  cfg: ParsedConfig,
  filter: FilterMatcher,
): number {
  let n = 0;
  const showSingle = (title: string, present: unknown) => {
    if (present && filter.match(title)) n += 1;
  };
  const showArr = (arr: unknown[]) => {
    if (arr.length > 0) n += 1;
  };
  showSingle("System", cfg.system);
  showSingle("Last revision", cfg.revision);
  showSingle("Last change", cfg.lastchange);
  showSingle("Theme", cfg.theme);
  showSingle("Diagnostic preferences", cfg.diag);
  showSingle("SSH host keys", cfg.sshdata);
  showArr(cfg.apikeys);
  showArr(cfg.interfaces);
  showArr(cfg.vlans);
  showArr(cfg.bridges);
  showSingle("Bridge (legacy)", cfg.legacy_bridge);
  showArr(cfg.proxyarp);
  showArr(cfg.gifs);
  showArr(cfg.gres);
  showArr(cfg.ppps);
  showArr(cfg.qinqs);
  showArr(cfg.laggs);
  showArr(cfg.wol);
  showArr(cfg.virtual_ips);
  showSingle("HA / CARP sync", cfg.hasync);
  showArr(cfg.gateways);
  showArr(cfg.gateway_groups);
  showArr(cfg.static_routes);
  showArr(cfg.firewall_rules);
  showArr(cfg.nat_rules);
  showArr(cfg.aliases);
  showArr(cfg.dhcp_servers);
  showSingle("DNS", cfg.dns);
  showArr(cfg.dhcp_relays);
  showArr(cfg.dyndns_entries);
  showArr(cfg.igmpproxy_entries);
  showArr(cfg.radvd_interfaces);
  showSingle("Notifications", cfg.notifications);
  showSingle("UPS monitoring", cfg.ups);
  showArr(cfg.voucher_rolls);
  showSingle("FTP proxy", cfg.ftpproxy);
  showSingle("NTP server", cfg.ntpd);
  showSingle("SNMP", cfg.snmpd);
  showSingle("Remote syslog", cfg.syslog);
  showArr(cfg.schedules);
  showArr(cfg.shaper_queues);
  showArr(cfg.dnshaper_pipes);
  if (cfg.lb_pools.length > 0 || cfg.lb_virtual_servers.length > 0) n += 1;
  showArr(cfg.captive_portal_zones);
  showArr(cfg.openvpn_servers);
  showArr(cfg.openvpn_clients);
  showArr(cfg.openvpn_cscs);
  showSingle("OpenVPN server (wizard state)", cfg.ovpnserver_wizard);
  showSingle("L2TP server", cfg.l2tp);
  showArr(cfg.pppoe_servers);
  showArr(cfg.ipsec_phase1);
  showArr(cfg.ipsec_phase2);
  showArr(cfg.ipsec_psks);
  showArr(cfg.certificate_authorities);
  showArr(cfg.certificates);
  showArr(cfg.crls);
  showSingle("Installed packages", cfg.installedpackages);
  showArr(cfg.users);
  showArr(cfg.groups);
  showArr(cfg.authservers);
  showArr(cfg.sysctl);
  showArr(cfg.cron);
  showArr(cfg.interface_groups);
  showSingle("Shaper wizard state", cfg.ezshaper);
  showSingle("DHCP backend", cfg.dhcp_backend);
  showArr(cfg.unrecognized_sections);
  return n;
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
  // v0.14.0
  "Last change": "lastchange",
  Theme: "theme",
  "Diagnostic preferences": "diag",
  "SSH host keys": "sshdata",
  "API keys": "apikeys",
  "Bridge (legacy)": "legacy_bridge",
  "Interface groups": "interface_groups",
  "Proxy ARP": "proxyarp",
  "OpenVPN server (wizard state)": "ovpnserver_wizard",
  "L2TP server": "l2tp",
  "PPPoE servers": "pppoe_servers",
  "Shaper wizard state": "ezshaper",
  "DHCP backend": "dhcp_backend",
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

function TableOfContents({
  cfg,
  orientation = "horizontal",
  activeId,
}: {
  cfg: ParsedConfig;
  orientation?: "horizontal" | "vertical";
  activeId?: string | null;
}) {
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
  if (cfg.apikeys.length) entries.push(["API keys", cfg.apikeys.length]);
  if (cfg.sshdata) entries.push(["SSH host keys", 1]);
  if (cfg.interface_groups.length)
    entries.push(["Interface groups", cfg.interface_groups.length]);
  if (cfg.proxyarp.length) entries.push(["Proxy ARP", cfg.proxyarp.length]);
  if (cfg.pppoe_servers.length)
    entries.push(["PPPoE servers", cfg.pppoe_servers.length]);
  if (cfg.l2tp) entries.push(["L2TP server", 1]);
  if (cfg.ovpnserver_wizard)
    entries.push(["OpenVPN server (wizard state)", 1]);
  if (cfg.ezshaper) entries.push(["Shaper wizard state", 1]);
  if (cfg.legacy_bridge) entries.push(["Bridge (legacy)", 1]);
  if (cfg.diag) entries.push(["Diagnostic preferences", 1]);
  if (cfg.theme) entries.push(["Theme", 1]);
  if (cfg.dhcp_backend) entries.push(["DHCP backend", 1]);
  if (cfg.lastchange) entries.push(["Last change", 1]);
  if (cfg.unrecognized_sections.length)
    entries.push([
      "Other sections (raw XML)",
      cfg.unrecognized_sections.length,
    ]);

  if (orientation === "vertical") {
    return (
      <nav
        aria-label="Sections"
        className="flex flex-col gap-0.5 rounded border border-border bg-muted/30 p-2 text-xs"
      >
        <div className="mb-1 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-fg">
          {cfg.config_version
            ? `Schema v${cfg.config_version}`
            : "Sections"}
        </div>
        {entries.map(([title, count]) => {
          const id = sectionId(title);
          const active = activeId === id;
          return (
            <a
              key={title}
              href={`#${id}`}
              className={cn(
                "flex items-center justify-between gap-2 rounded border-l-2 border-transparent px-2 py-1 text-muted-fg hover:bg-muted hover:text-fg",
                active && "border-accent bg-muted font-medium text-fg",
              )}
            >
              <span className="truncate">{title}</span>
              <span className="shrink-0 text-[10px] opacity-70">({count})</span>
            </a>
          );
        })}
      </nav>
    );
  }

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
  // Normalise em / en dashes to a plain hyphen BEFORE collapsing
  // whitespace — otherwise ``"IPsec — phase 1"`` becomes
  // ``section-ipsec-—-phase-1`` with a literal U+2014 in the DOM id,
  // which breaks any caller that tries to construct the same id
  // from a known-string table (e.g. ``SCOPE_TO_SECTION_ID`` in
  // xref.ts for the deep-link-into-collapsed-card fallback).
  return (
    "section-" +
    title
      .toLowerCase()
      .replace(/[—–]/g, "-")
      .replace(/\s+/g, "-")
      .replace(/[()]/g, "")
      .replace(/-{2,}/g, "-")
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
          s.webgui ? (
            <span className="inline-flex items-center gap-2">
              <span>
                {s.webgui.protocol ?? "?"} :{s.webgui.port ?? "?"}
              </span>
              {s.webgui.ssl_certref && (
                <Xref kind="cert" k={s.webgui.ssl_certref} label="Cert" />
              )}
            </span>
          ) : (
            "—"
          ),
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
      rowKeys={rows.map((r) => r.key)}
      rowIds={rows.map((r) => itemId("interface", r.key))}
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
      rowIds={rows.map((r) => itemId("gateway", r.name))}
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
      rowIds={rows.map((r) => itemId("gateway_group", r.name))}
      rows={rows.map((r) => [
        r.name,
        r.trigger ?? "—",
        <span key="m" className="inline-flex flex-wrap gap-1">
          {r.members.length
            ? r.members.map((m) => (
                <Xref key={m} kind="gateway" k={m} />
              ))
            : "—"}
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
        <Xref key="g" kind="gateway" k={r.gateway} />,
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
        "Gateway",
        "Sched",
        "Description",
      ]}
      rowKeys={rows.map((r) => r.key)}
      rowIds={rows.map((r) => rowAnchorId("rule", r.key))}
      rows={rows.map((r, i) => [
        <span key="n" className="font-mono text-xs text-muted-fg">
          {i + 1}
        </span>,
        <ActionPill key="a" type={r.type} />,
        <InterfaceChip key="i" name={r.interface} />,
        <span key="p" className="font-mono text-xs">
          {r.protocol ?? "any"}
        </span>,
        <EndpointCell key="s" e={r.source} />,
        <EndpointCell key="dst" e={r.destination} />,
        <Xref key="gw" kind="gateway" k={r.gateway} />,
        <Xref key="sch" kind="schedule" k={r.schedule} />,
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
      rowIds={rows.map((r) => rowAnchorId("nat", r.key))}
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
        <EndpointCell key="s" e={r.source} />,
        <EndpointCell key="dst" e={r.destination} />,
        r.target ? (
          <Xref
            key="t"
            kind="alias"
            k={r.target}
            fallback={
              <span className="font-mono text-xs">{r.target}</span>
            }
          />
        ) : (
          "—"
        ),
        r.local_port ?? "—",
        <span key="d" className="flex items-center gap-1">
          {r.descr ?? "—"}
          {r.disabled && <Badge tone="muted">disabled</Badge>}
        </span>,
      ])}
    />
  );
}

/** Renders a firewall-rule or NAT-rule endpoint (source / destination).
 *
 *  Before v0.18.0 this was a plain-text helper (``endpointStr``).
 *  That stranded alias references — ``address: "RFC1918"`` where
 *  ``RFC1918`` is a defined alias rendered as text, no click-through
 *  to the alias definition. Now we consult the xref index: if the
 *  ``address`` resolves to an alias, we render an ``<Xref kind="alias">``
 *  chip; otherwise it falls back to the raw string.
 *
 *  ``network`` always wins over ``address`` in pfSense's endpoint
 *  shape (``network`` = "lan subnet" / "wan net" / etc., ``address`` =
 *  literal or alias). Only ``address`` can be an alias — ``network``
 *  is always a special keyword. So alias-lookup runs on ``address``
 *  only.
 *
 *  ``not_`` prefixes a muted ``!`` so negated rules stay obvious. */
function EndpointCell({ e }: { e: Endpoint }) {
  if (e.any_) {
    return (
      <span className="font-mono text-xs">
        {e.not_ ? "!" : ""}any
      </span>
    );
  }
  const bang = e.not_ ? (
    <span className="font-mono text-xs font-semibold text-warn">!</span>
  ) : null;
  // Resolution order for ``e.address``: alias → interface → interface
  // group → plain text. v0.18.0 only tried alias, so a rule whose
  // source was literally ``"lan"`` or ``"opt3"`` (a bare interface
  // reference, which pfSense does allow) degraded to raw text with
  // no click-through. Chain the fallbacks so the chip always wins
  // when the token matches something in the xref index.
  const host: ReactNode = e.network ? (
    <span className="font-mono text-xs">{e.network}</span>
  ) : e.address ? (
    <Xref
      kind="alias"
      k={e.address}
      fallback={
        <Xref
          kind="interface"
          k={e.address}
          fallback={
            <Xref
              kind="interface_group"
              k={e.address}
              fallback={
                <span className="font-mono text-xs">{e.address}</span>
              }
            />
          }
        />
      }
    />
  ) : (
    <span className="font-mono text-xs">?</span>
  );
  return (
    <span className="inline-flex items-center gap-1">
      {bang}
      {host}
      {e.port ? (
        <span className="font-mono text-xs text-muted-fg">:{e.port}</span>
      ) : null}
    </span>
  );
}

function AliasesTable({ rows }: { rows: Alias[] }) {
  return (
    <Table
      headers={["Name", "Type", "Entries", "Description"]}
      rowKeys={rows.map((r) => r.name)}
      rowIds={rows.map((r) => itemId("alias", r.name))}
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
          <div className="mb-1 flex items-center gap-1 text-sm font-medium">
            <span>DHCP on</span>
            <InterfaceChip name={s.interface} />
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
      headers={["Name", "UID", "Scope", "Groups", "Certs", "Password", "Expires"]}
      rowKeys={rows.map((u) => u.name)}
      rowIds={rows.map((u) => itemId("user", u.name))}
      rows={rows.map((u) => [
        u.name,
        u.uid ?? "—",
        u.scope ?? "—",
        <span key="g" className="inline-flex flex-wrap gap-1">
          {u.groups.length
            ? u.groups.map((g) => <Xref key={g} kind="group" k={g} />)
            : "—"}
        </span>,
        <span key="c" className="inline-flex flex-wrap gap-1">
          {u.certrefs.length
            ? u.certrefs.map((c) => <Xref key={c} kind="cert" k={c} />)
            : "—"}
        </span>,
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
      rowKeys={rows.map((g) => g.name)}
      rowIds={rows.map((g) => itemId("group", g.name))}
      rows={rows.map((g) => [
        g.name,
        g.gid ?? "—",
        g.scope ?? "—",
        <span key="m" className="inline-flex flex-wrap gap-1">
          {g.members.length
            ? g.members.map((m) => <Xref key={m} kind="user" k={m} />)
            : "—"}
        </span>,
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
      rowKeys={rows.map((a) => a.name)}
      rowIds={rows.map((a) => itemId("authserver", a.name))}
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
      rowKeys={rows.map((v) => v.vlanif ?? v.key)}
      rowIds={rows.map((v) =>
        v.vlanif ? itemId("vlan", v.vlanif) : undefined,
      )}
      rows={rows.map((v) => [
        v.if_ ? <InterfaceChip key="p" name={v.if_} /> : "—",
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
        t.if_ ? <InterfaceChip key="i" name={t.if_} /> : "—",
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
        p.if_ ? <InterfaceChip key="i" name={p.if_} /> : "—",
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
        q.if_ ? <InterfaceChip key="p" name={q.if_} /> : "—",
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
        r.interface.length > 0 ? (
          <span key="i" className="inline-flex flex-wrap gap-1">
            {r.interface.map((name) => (
              <InterfaceChip key={name} name={name} />
            ))}
          </span>
        ) : (
          "—"
        ),
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
      rowKeys={rows.map((s) => s.name)}
      rowIds={rows.map((s) => itemId("schedule", s.name))}
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
        q.interface ? <InterfaceChip key="i" name={q.interface} /> : "—",
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
            rowKeys={pools.map((p) => p.name)}
            rowIds={pools.map((p) => itemId("lb_pool", p.name))}
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
            rowKeys={vservers.map((v) => v.name)}
            rows={vservers.map((v) => [
              v.name,
              v.ipaddr ?? "—",
              v.port ?? "—",
              v.mode ?? "—",
              <Xref key="p" kind="lb_pool" k={v.poolname} />,
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
        <span key="i" className="inline-flex flex-wrap gap-1">
          {z.interfaces.length
            ? z.interfaces.map((x) => (
                <InterfaceChip key={x} name={x} />
              ))
            : "—"}
        </span>,
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
        "Iface",
        "Proto / port",
        "Tunnel",
        "CA / Cert",
        "Auth",
        "Cipher",
        "TLS",
      ]}
      rowKeys={rows.map((s) => s.vpnid)}
      rowIds={rows.map((s) => itemId("openvpn_server", s.vpnid))}
      rows={rows.map((s) => [
        s.vpnid,
        s.description ?? "—",
        s.mode ?? "—",
        <InterfaceChip key="if" name={s.interface} />,
        `${s.protocol ?? "?"} :${s.local_port ?? "?"}`,
        s.tunnel_network ?? s.tunnel_networkv6 ?? "—",
        <span key="pki" className="inline-flex flex-wrap gap-1">
          <Xref kind="ca" k={s.caref} label="CA" />
          <Xref kind="cert" k={s.certref} label="Cert" />
        </span>,
        <span key="am" className="inline-flex flex-wrap gap-1">
          {s.authmode.length
            ? s.authmode.map((n) => (
                <Xref key={n} kind="authserver" k={n} />
              ))
            : "—"}
        </span>,
        s.crypto ?? "—",
        s.tls === "***redacted***" ? <Redacted /> : "—",
      ])}
    />
  );
}

function OpenVpnClientsTable({ rows }: { rows: OpenVpnClient[] }) {
  return (
    <Table
      headers={["#", "Description", "Mode", "Iface", "Server", "Tunnel", "CA / Cert", "Cipher", "TLS"]}
      rowKeys={rows.map((c) => c.vpnid)}
      rowIds={rows.map((c) => itemId("openvpn_client", c.vpnid))}
      rows={rows.map((c) => [
        c.vpnid,
        c.description ?? "—",
        c.mode ?? "—",
        <InterfaceChip key="if" name={c.interface} />,
        c.server_addr
          ? `${c.server_addr}:${c.server_port ?? "?"}`
          : "—",
        c.tunnel_network ?? "—",
        <span key="pki" className="inline-flex flex-wrap gap-1">
          <Xref kind="ca" k={c.caref} label="CA" />
          <Xref kind="cert" k={c.certref} label="Cert" />
        </span>,
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
        c.server_list.length > 0 ? (
          <XrefList key="s" kind="openvpn_server" keys={c.server_list} />
        ) : (
          "—"
        ),
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
        "Iface",
        "Remote gw",
        "Auth",
        "PSK",
        "Encryption set",
        "Description",
      ]}
      rowKeys={rows.map((p) => p.ikeid)}
      rowIds={rows.map((p) => itemId("ipsec_phase1", p.ikeid))}
      rows={rows.map((p) => [
        p.ikeid,
        p.iketype ?? "—",
        <InterfaceChip key="if" name={p.interface} />,
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
      rowKeys={rows.map((p) => p.uniqid)}
      rows={rows.map((p) => [
        p.uniqid,
        <Xref key="ike" kind="ipsec_phase1" k={p.ikeid} />,
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
      rowKeys={rows.map((c) => c.refid)}
      rowIds={rows.map((c) => itemId("ca", c.refid))}
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
        "Issued by",
        "Type",
        "SANs",
        "Issuer",
        "Expires",
        "Private key",
      ]}
      rowKeys={rows.map((c) => c.refid)}
      rowIds={rows.map((c) => itemId("cert", c.refid))}
      rows={rows.map((c) => [
        <CertIdentity key="i" refid={c.refid} meta={c.metadata} />,
        c.descr ?? "—",
        <Xref key="ca" kind="ca" k={c.caref} />,
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
  if (ip.wireguard) n += 1;
  if (ip.snort) n += 1;
  if (ip.miniupnpd) n += 1;
  if (ip.avahi) n += 1;
  if (ip.openvpn_client_export) n += 1;
  if (ip.shellcmd) n += 1;
  n += ip.unknown.length;
  return n;
}

function PackagesPanel({ ip }: { ip: InstalledPackages }) {
  return (
    <div className="space-y-4">
      {ip.pfblockerng && <PfBlockerNgPanel p={ip.pfblockerng} />}
      {ip.haproxy && <HaProxyPanel p={ip.haproxy} />}
      {ip.suricata && <SuricataPanel p={ip.suricata} />}
      {ip.snort && <SnortPanel p={ip.snort} />}
      {ip.acme && <AcmePanel p={ip.acme} />}
      {ip.squid && <SquidPanel p={ip.squid} />}
      {ip.freeradius && <FreeRadiusPanel p={ip.freeradius} />}
      {ip.telegraf && <TelegrafPanel p={ip.telegraf} />}
      {ip.frr && <FrrPanel p={ip.frr} />}
      {ip.zabbix && <ZabbixPanel p={ip.zabbix} />}
      {ip.wireguard && <WireGuardPanel p={ip.wireguard} />}
      {ip.miniupnpd && <MiniUpnpdPanel p={ip.miniupnpd} />}
      {ip.avahi && <AvahiPanel p={ip.avahi} />}
      {ip.openvpn_client_export && (
        <OpenvpnClientExportPanel p={ip.openvpn_client_export} />
      )}
      {ip.shellcmd && <ShellCmdPanel p={ip.shellcmd} />}
      {ip.unknown.length > 0 && <UnknownPackagesList rows={ip.unknown} />}
    </div>
  );
}

function PfBlockerNgPanel({ p }: { p: PfBlockerNgConfig }) {
  const subFeatures = [
    p.topspammers_present && "Top spammers",
    p.blacklist_present && "Blacklist",
    p.safesearch_present && "SafeSearch",
    p.reputation_present && "Reputation",
    p.dnsbl_safesearch_present && "DNSBL SafeSearch",
    p.global_present && "Global",
  ].filter((x): x is string => Boolean(x));
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
          ...(subFeatures.length > 0
            ? ([["Sub-features", subFeatures.join(", ")]] as [
                string,
                React.ReactNode,
              ][])
            : []),
          ...(p.geoip_configured
            ? ([
                [
                  "GeoIP continents",
                  p.geoip_continents.length > 0
                    ? p.geoip_continents.join(", ")
                    : "configured",
                ],
              ] as [string, React.ReactNode][])
            : []),
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
            rowKeys={p.frontends.map((f) => f.name)}
            rows={p.frontends.map((f) => [
              f.name,
              f.type ?? "—",
              f.addresses.join(", ") || f.extaddr || "—",
              <Xref key="db" kind="haproxy_backend" k={f.default_backend} />,
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
            rowKeys={p.backends.map((b) => b.name)}
            rowIds={p.backends.map((b) => itemId("haproxy_backend", b.name))}
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

/** Short-form WireGuard public key with click-to-copy. The keys are
 *  44 chars of base64 so the raw string overflows most table cells.
 *  Before v0.20.0 we rendered ``{key.slice(0,12)}…`` inside a span
 *  with ``truncate`` + a ``title`` attribute — the full value only
 *  surfaced on hover (no keyboard path) and couldn't be copied
 *  without a DOM inspector. Operators routinely cross-reference
 *  keys between tunnels and peers, so expose a real copy button. */
function CopyableKey({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  // Track the reset timer so we can cancel it on unmount or re-copy
  // — otherwise a rapid click sequence (or unmount mid-timeout)
  // leaves a pending setCopied(false) pointed at a stale component.
  const resetTimerRef = useRef<number | null>(null);
  useEffect(() => {
    return () => {
      if (resetTimerRef.current !== null) {
        window.clearTimeout(resetTimerRef.current);
      }
    };
  }, []);
  const hasClipboard =
    typeof navigator !== "undefined" && Boolean(navigator.clipboard);
  return (
    <button
      type="button"
      disabled={!hasClipboard}
      className="inline-flex items-center gap-1 rounded font-mono text-xs text-muted-fg transition-colors hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 disabled:cursor-default disabled:hover:text-muted-fg"
      title={
        !hasClipboard
          ? value
          : copied
            ? "Copied!"
            : `${value} — click to copy`
      }
      onClick={(e) => {
        e.stopPropagation();
        if (!navigator.clipboard) return;
        void navigator.clipboard.writeText(value).then(() => {
          setCopied(true);
          if (resetTimerRef.current !== null) {
            window.clearTimeout(resetTimerRef.current);
          }
          resetTimerRef.current = window.setTimeout(() => {
            resetTimerRef.current = null;
            setCopied(false);
          }, 1200);
        });
      }}
    >
      <span>{value.slice(0, 12)}…</span>
      {copied ? (
        <Check aria-hidden="true" className="h-3 w-3 text-success" />
      ) : (
        <Copy aria-hidden="true" className="h-3 w-3" />
      )}
      <span className="sr-only">Copy public key</span>
    </button>
  );
}

function WireGuardPanel({ p }: { p: WireGuardConfig }) {
  return (
    <PackageCard title="WireGuard">
      {p.tunnels.length === 0 && p.peers.length === 0 && (
        <div className="text-xs text-muted-fg">
          Package installed but no tunnels or peers configured.
        </div>
      )}
      {p.tunnels.length > 0 && (
        <div className="mb-2">
          <div className="mb-1 text-xs uppercase text-muted-fg">
            Tunnels ({p.tunnels.length})
          </div>
          <Table
            headers={[
              "Name",
              "Enabled",
              "Addresses",
              "DNS",
              "Listen port",
              "Public key",
              "Private key",
              "Description",
            ]}
            rowKeys={p.tunnels.map((t) => t.name)}
            rows={p.tunnels.map((t) => [
              <span key="n" className="font-mono text-xs">
                {t.name}
              </span>,
              <StatusPill key="e" enabled={t.enabled} />,
              t.addresses.length > 0 ? (
                <span key="a" className="font-mono text-xs">
                  {t.addresses.join(", ")}
                </span>
              ) : (
                "—"
              ),
              t.dns ? (
                <span key="dns" className="font-mono text-xs">
                  {t.dns}
                </span>
              ) : (
                "—"
              ),
              t.listen_port ?? "—",
              t.public_key ? (
                <CopyableKey key="pub" value={t.public_key} />
              ) : (
                "—"
              ),
              t.private_key === "***redacted***" ? <Redacted /> : "—",
              t.descr ?? "—",
            ])}
          />
        </div>
      )}
      {p.peers.length > 0 && (
        <div>
          <div className="mb-1 text-xs uppercase text-muted-fg">
            Peers ({p.peers.length})
          </div>
          <Table
            headers={[
              "Description",
              "Enabled",
              "Tunnel",
              "Endpoint",
              "Allowed IPs",
              "Public key",
              "PSK",
            ]}
            rows={p.peers.map((pe) => [
              pe.descr ?? "—",
              <StatusPill key="e" enabled={pe.enabled} />,
              pe.tun ?? "—",
              pe.endpoint
                ? `${pe.endpoint}${pe.port ? ":" + pe.port : ""}`
                : "—",
              pe.allowed_ips.length > 0 ? (
                <span key="a" className="font-mono text-xs">
                  {pe.allowed_ips.join(", ")}
                </span>
              ) : (
                "—"
              ),
              pe.public_key ? (
                <CopyableKey key="pub" value={pe.public_key} />
              ) : (
                "—"
              ),
              pe.preshared_key === "***redacted***" ? <Redacted /> : "—",
            ])}
          />
        </div>
      )}
    </PackageCard>
  );
}

function SnortPanel({ p }: { p: SnortConfig }) {
  return (
    <PackageCard title="Snort (IDS/IPS)">
      <Dl
        items={[
          [
            "Subscription key",
            p.oinkmaster_configured ? <Redacted /> : "not set",
          ],
          [
            "Community rules",
            <StatusPill key="cr" enabled={p.snort_community_rules_enabled} />,
          ],
          [
            "Emerging Threats",
            <StatusPill key="et" enabled={p.emerging_threats_enabled} />,
          ],
        ]}
      />
      {p.interfaces.length > 0 && (
        <div className="mt-2">
          <div className="mb-1 text-xs uppercase text-muted-fg">
            Monitored interfaces ({p.interfaces.length})
          </div>
          <Table
            headers={[
              "Interface",
              "Enabled",
              "Block offenders",
              "IPS mode",
              "Categories",
              "Description",
            ]}
            rows={p.interfaces.map((i) => [
              i.interface ? (
                <InterfaceChip key="i" name={i.interface} />
              ) : (
                i.uuid
              ),
              <StatusPill key="e" enabled={i.enable} />,
              <StatusPill
                key="bo"
                enabled={i.blockoffenders7}
                labels={{ on: "yes", off: "no" }}
              />,
              i.ips_mode ?? "—",
              i.categories.length > 0
                ? `${i.categories.length} ruleset${i.categories.length === 1 ? "" : "s"}`
                : "—",
              i.descr ?? "—",
            ])}
          />
        </div>
      )}
    </PackageCard>
  );
}

function MiniUpnpdPanel({ p }: { p: MiniUpnpdConfig }) {
  return (
    <PackageCard title="miniUPnPd (UPnP & NAT-PMP)">
      <Dl
        items={[
          ["Enabled", <StatusPill key="e" enabled={p.enable} />],
          ["UPnP", <StatusPill key="u" enabled={p.enable_upnp} />],
          ["NAT-PMP", <StatusPill key="n" enabled={p.enable_natpmp} />],
          ["Internal interfaces", p.iface_array ?? "—"],
          ["External interface", p.ext_iface ?? "—"],
          ["Download", p.download ? `${p.download} kbit/s` : "—"],
          ["Upload", p.upload ? `${p.upload} kbit/s` : "—"],
        ]}
      />
      {p.permit_rules.length > 0 && (
        <div className="mt-2">
          <div className="mb-1 text-xs uppercase text-muted-fg">
            Permit rules ({p.permit_rules.length})
          </div>
          <ul className="space-y-0.5 text-xs">
            {p.permit_rules.map((r, i) => (
              <li key={i} className="font-mono">
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}
    </PackageCard>
  );
}

function AvahiPanel({ p }: { p: AvahiConfig }) {
  return (
    <PackageCard title="Avahi (mDNS reflector)">
      <Dl
        items={[
          ["Enabled", <StatusPill key="e" enabled={p.enable} />],
          ["Reflector", <StatusPill key="r" enabled={p.reflector} />],
          [
            "IPv4",
            <StatusPill
              key="v4"
              enabled={p.ipv4_enabled}
              labels={{ on: "yes", off: "no" }}
            />,
          ],
          [
            "IPv6",
            <StatusPill
              key="v6"
              enabled={p.ipv6_enabled}
              labels={{ on: "yes", off: "no" }}
            />,
          ],
          ["Reflect IP", p.reflect_ipv ?? "—"],
          [
            "Wide-area",
            <StatusPill
              key="wa"
              enabled={p.wide_area}
              labels={{ on: "yes", off: "no" }}
            />,
          ],
          [
            "Publish workstation",
            <StatusPill
              key="pw"
              enabled={p.publish_workstation}
              labels={{ on: "yes", off: "no" }}
            />,
          ],
          [
            "Publish addresses",
            <StatusPill
              key="pa"
              enabled={p.publish_addresses}
              labels={{ on: "yes", off: "no" }}
            />,
          ],
          ["Interfaces", p.interfaces ?? "—"],
          ["Deny interfaces", p.allow_deny_interfaces ?? "—"],
          ["Browse domains", p.browse_domains ?? "—"],
          ["Cache max entries", p.cache_entries_max ?? "—"],
        ]}
      />
    </PackageCard>
  );
}

function OpenvpnClientExportPanel({
  p,
}: {
  p: OpenvpnClientExportConfig;
}) {
  return (
    <PackageCard title="OpenVPN Client Export">
      <Dl
        items={[
          [
            "Use random local port",
            <StatusPill key="r" enabled={p.use_random_local_port} />,
          ],
          [
            "Silent install",
            <StatusPill key="s" enabled={p.silent_install} />,
          ],
          ["Interface selection", p.interface_selection ?? "—"],
          ["Hostname", p.hostname ?? "—"],
          ["Cert subject (country)", p.ovpnexportcountry ?? "—"],
          ["Cert subject (state)", p.ovpnexportstate ?? "—"],
          ["Cert subject (city)", p.ovpnexportcity ?? "—"],
        ]}
      />
      {p.servers.length > 0 && (
        <div className="mt-2">
          <div className="mb-1 text-xs uppercase text-muted-fg">
            Per-server overrides ({p.servers.length})
          </div>
          <Table
            headers={[
              "VPN id",
              "Host address",
              "Verify CN",
              "Block outside DNS",
              "Token",
              "PKCS#11",
              "Bind mode",
              "Silent install",
            ]}
            rowKeys={p.servers.map((s) => s.key)}
            rows={p.servers.map((s) => [
              <Xref
                key="v"
                kind="openvpn_server"
                k={s.vpnid}
                fallback={
                  <span className="font-mono text-xs">{s.vpnid ?? s.key}</span>
                }
              />,
              s.useaddr ?? "—",
              s.verifyservercn ?? "—",
              <StatusPill
                key="bd"
                enabled={s.blockoutsidedns}
                labels={{ on: "yes", off: "no" }}
              />,
              <StatusPill
                key="tk"
                enabled={s.usetoken}
                labels={{ on: "yes", off: "no" }}
              />,
              <StatusPill
                key="pk"
                enabled={s.usepkcs11}
                labels={{ on: "yes", off: "no" }}
              />,
              s.bindmode ?? "—",
              <StatusPill
                key="si"
                enabled={s.silent_install}
                labels={{ on: "yes", off: "no" }}
              />,
            ])}
          />
        </div>
      )}
    </PackageCard>
  );
}

function ShellCmdPanel({ p }: { p: ShellCmdSettings }) {
  return (
    <PackageCard title="Shellcmd (boot / filter hooks)">
      {p.entries.length === 0 ? (
        <div className="text-xs text-muted-fg">No commands configured.</div>
      ) : (
        <Table
          headers={["Type", "Command", "Disabled", "Description"]}
          rows={p.entries.map((e) => [
            <span key="t" className="font-mono text-xs">
              {e.cmdtype ?? "shellcmd"}
            </span>,
            <span key="c" className="break-all font-mono text-xs">
              {e.cmd}
            </span>,
            e.disabled ? "yes" : "",
            e.descr ?? "—",
          ])}
        />
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
  // When an xref index is in scope AND the name resolves as either a
  // physical interface OR a named interface-group, render as a
  // navigable chip. Firewall rules' ``<interface>`` field accepts
  // either kind, so we try ``interface`` first and fall back to
  // ``interface_group`` before degrading to a plain span. The hashed
  // group-color classes are preserved in both linked cases so
  // "LAN is always green" still holds regardless of which kind
  // resolved.
  const c = interfaceChipClasses(name);
  const plain = (
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
  return (
    <Xref
      kind="interface"
      k={name}
      label={interfaceLabel(name)}
      className={cn(c.fg, c.border, className)}
      fallback={
        <Xref
          kind="interface_group"
          k={name}
          label={interfaceLabel(name)}
          className={cn(c.fg, c.border, className)}
          fallback={plain}
        />
      }
    />
  );
});

/** Colored pill for firewall-rule action type. */
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
      rowKeys={rows.map((c) => c.refid)}
      rowIds={rows.map((c) => itemId("crl", c.refid))}
      rows={rows.map((c) => [
        c.descr ?? "—",
        c.method ?? "—",
        <Xref key="ca" kind="ca" k={c.caref} />,
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
                p.squid.active_interface ? (
                  <span key="l" className="inline-flex items-center gap-1">
                    <InterfaceChip name={p.squid.active_interface} />
                    <span className="font-mono text-xs">
                      :{p.squid.proxy_port ?? "3128"}
                    </span>
                  </span>
                ) : (
                  "—"
                ),
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
                p.squid.allow_interface.length > 0 ? (
                  <span key="ai" className="flex flex-wrap gap-1">
                    {p.squid.allow_interface.map((i) => (
                      <InterfaceChip key={i} name={i} />
                    ))}
                  </span>
                ) : (
                  "—"
                ),
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
      {p.auth && (
        <div className="mt-2">
          <div className="mb-1 text-xs uppercase text-muted-fg">
            Authentication
          </div>
          <Dl
            items={[
              ["Method", p.auth.auth_method ?? "—"],
              ["LDAP server", p.auth.ldap_server ?? "—"],
              ["LDAP bind DN", p.auth.ldap_binddn ?? "—"],
              [
                "LDAP bind password",
                p.auth.ldap_pass === "***redacted***" ? <Redacted /> : "—",
              ],
              ["LDAP base", p.auth.ldap_search_base ?? "—"],
              ["LDAP filter", p.auth.ldap_filter ?? "—"],
              ["RADIUS server", p.auth.radius_server ?? "—"],
              [
                "RADIUS secret",
                p.auth.radius_secret === "***redacted***" ? <Redacted /> : "—",
              ],
              ["NTLM user", p.auth.nt_user ?? "—"],
              [
                "NTLM password",
                p.auth.nt_pass === "***redacted***" ? <Redacted /> : "—",
              ],
            ]}
          />
        </div>
      )}
      {(p.cache_present || p.remote_present || p.antivirus_present) && (
        <div className="mt-2 flex flex-wrap gap-1 text-xs">
          <span className="text-muted-fg">Sub-features configured:</span>
          {p.cache_present && <Badge tone="muted">cache</Badge>}
          {p.remote_present && <Badge tone="muted">remote ACL</Badge>}
          {p.antivirus_present && <Badge tone="muted">antivirus</Badge>}
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
          ["Username", <RV key="u" v={p.username} />],
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
      {p.ospfd_interfaces.length > 0 && (
        <div className="mt-2">
          <div className="mb-1 text-xs uppercase text-muted-fg">
            OSPFv3 interfaces
          </div>
          <Table
            headers={[
              "Interface",
              "Area",
              "Cost",
              "Hello / Dead",
              "MD5",
            ]}
            rows={p.ospfd_interfaces.map((i) => [
              <InterfaceChip key="i" name={i.interface} />,
              i.area ?? "—",
              i.cost ?? "—",
              `${i.hello_interval ?? "?"} / ${i.dead_interval ?? "?"}`,
              i.md5_password === "***redacted***" ? <Redacted /> : "—",
            ])}
          />
        </div>
      )}
      {(p.ospfd_present ||
        p.ospfd_areas_present ||
        p.ospfd_interfaces_present ||
        p.global_acls_present ||
        p.global_prefixes_present ||
        p.bgp6_present) && (
        <div className="mt-2 flex flex-wrap gap-1 text-xs">
          <span className="text-muted-fg">
            IPv6 OSPF + global policy:
          </span>
          {p.ospfd_present && <Badge tone="muted">OSPFd</Badge>}
          {p.ospfd_areas_present && <Badge tone="muted">OSPFd areas</Badge>}
          {p.ospfd_interfaces_present && (
            <Badge tone="muted">OSPFd interfaces</Badge>
          )}
          {p.global_acls_present && <Badge tone="muted">ACLs</Badge>}
          {p.global_prefixes_present && (
            <Badge tone="muted">prefix lists</Badge>
          )}
          {p.bgp6_present && <Badge tone="muted">BGP6d</Badge>}
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

// ---------- v0.14.0: new section renderers --------------------------------

function SshDataPanel({ s }: { s: SshData }) {
  // Pair entries by filename stem so each algorithm shows its private
  // + public halves on one row. pfSense writes the pair as
  // ``ssh_host_{algo}_key`` (private) + ``ssh_host_{algo}_key.pub``.
  type Pair = { stem: string; priv?: SshHostKeyFile; pub?: SshHostKeyFile };
  const byStem = new Map<string, Pair>();
  for (const k of s.keys) {
    const stem = k.filename.replace(/\.pub$/, "");
    const p = byStem.get(stem) ?? { stem };
    if (k.is_private) p.priv = k;
    else p.pub = k;
    byStem.set(stem, p);
  }
  const rows = Array.from(byStem.values()).sort((a, b) =>
    a.stem.localeCompare(b.stem),
  );
  if (rows.length === 0) {
    return <div className="text-sm text-muted-fg">No host-key material.</div>;
  }
  return (
    <Table
      headers={["Algorithm / filename", "Private key", "Public half"]}
      rowKeys={rows.map((r) => r.stem)}
      rows={rows.map((r) => [
        <span key="n" className="font-mono text-xs">
          {r.stem}
        </span>,
        r.priv?.xmldata === "***redacted***" ? (
          <Redacted key="p" />
        ) : r.priv?.xmldata ? (
          <span key="p" className="font-mono text-xs">
            (present)
          </span>
        ) : (
          <span key="p" className="text-muted-fg">
            —
          </span>
        ),
        r.pub?.xmldata ? (
          <span
            key="pb"
            className="truncate font-mono text-[11px] text-muted-fg"
            title={r.pub.xmldata}
          >
            {r.pub.xmldata.slice(0, 64)}
            {r.pub.xmldata.length > 64 ? "…" : ""}
          </span>
        ) : (
          <span key="pb" className="text-muted-fg">
            —
          </span>
        ),
      ])}
    />
  );
}

function DiagPanel({ s }: { s: DiagPreferences }) {
  // All three fields are pfSense webGUI preferences — none affect
  // how this backup viewer renders. Clarify with a parenthetical
  // so operators don't mistake "Show-all-passwords: on" for a
  // redaction-bypass switch here.
  return (
    <Dl
      items={[
        [
          "IPv6 NAT UI (pfSense webGUI pref)",
          <StatusPill
            key="i"
            enabled={s.ipv6nat}
            labels={{ on: "on", off: "off" }}
          />,
        ],
        [
          "Show-no-aliases (pfSense webGUI pref)",
          <StatusPill
            key="s"
            enabled={s.shownoaliases}
            labels={{ on: "on", off: "off" }}
          />,
        ],
        [
          "Show-all-passwords (pfSense webGUI pref)",
          <StatusPill
            key="p"
            enabled={s.showallpasswords}
            labels={{ on: "on", off: "off" }}
          />,
        ],
      ]}
    />
  );
}

function ApiKeysTable({ rows }: { rows: ApiKeyEntry[] }) {
  return (
    <Table
      headers={["User", "Description", "Key", "Secret"]}
      rowKeys={rows.map((r) => r.key)}
      rows={rows.map((r) => [
        <Xref key="u" kind="user" k={r.username} />,
        r.descr ?? "—",
        <span key="k" className="font-mono text-xs">
          {r.apikey ?? "—"}
        </span>,
        <RV v={r.apisecret} key="s" />,
      ])}
    />
  );
}

function InterfaceGroupsTable({ rows }: { rows: InterfaceGroup[] }) {
  return (
    <Table
      headers={["Group", "Members", "Description"]}
      rowKeys={rows.map((r) => r.ifname)}
      rowIds={rows.map((r) => itemId("interface_group", r.ifname))}
      rows={rows.map((r) => [
        <span key="n" className="font-mono text-xs font-medium">
          {r.ifname}
        </span>,
        <span key="m" className="inline-flex flex-wrap gap-1">
          {r.members.length
            ? r.members.map((m) => <InterfaceChip key={m} name={m} />)
            : "—"}
        </span>,
        r.descr ?? "—",
      ])}
    />
  );
}

function ProxyArpTable({ rows }: { rows: ProxyArpEntry[] }) {
  return (
    <Table
      headers={["Interface", "Network", "Description"]}
      rowKeys={rows.map((r) => r.key)}
      rows={rows.map((r) => [
        <InterfaceChip key="i" name={r.interface} />,
        <span key="n" className="font-mono text-xs">
          {r.network ?? "—"}
        </span>,
        r.descr ?? "—",
      ])}
    />
  );
}

function OvpnServerWizardPanel({ w }: { w: OvpnServerWizard }) {
  return (
    <Dl
      items={[
        ["Wizard step", w.step ?? "—"],
        ["Description", w.description ?? "—"],
        ["CA cert", w.cacrt ? "captured" : "—"],
        [
          "CA private key",
          w.cakey === "***redacted***" ? <Redacted key="c" /> : "—",
        ],
        ["Server cert", w.crt ? "captured" : "—"],
        [
          "Server private key",
          w.key === "***redacted***" ? <Redacted key="k" /> : "—",
        ],
      ]}
    />
  );
}

function L2tpPanel({ c }: { c: L2tpConfig }) {
  return (
    <div className="space-y-3">
      <Dl
        items={[
          ["Mode", c.mode ?? "—"],
          ["Interface", <InterfaceChip key="i" name={c.interface} />],
          ["Local IP", c.localip ?? "—"],
          ["Remote IP pool", c.remoteip ?? "—"],
          [
            "RADIUS",
            c.radius_enabled ? (
              <span className="inline-flex items-center gap-2">
                <Badge tone="success">enabled</Badge>
                {c.radius_server ?? ""}
                {c.radius_secret === "***redacted***" && <Redacted />}
              </span>
            ) : (
              "disabled"
            ),
          ],
        ]}
      />
      {c.users.length > 0 && (
        <div>
          <div className="mb-1 text-xs uppercase text-muted-fg">
            Users ({c.users.length})
          </div>
          <Table
            headers={["Name", "IP", "Password"]}
            rowKeys={c.users.map((u) => u.name)}
            rows={c.users.map((u) => [
              u.name,
              u.ip ?? "—",
              <RV v={u.password} key="p" />,
            ])}
          />
        </div>
      )}
    </div>
  );
}

function PppoeServersTable({ rows }: { rows: PppoeServerEntry[] }) {
  return (
    <div className="space-y-3">
      {rows.map((p) => (
        <div
          key={p.key}
          className="rounded border border-border/70 bg-muted/20 p-2"
        >
          <div className="mb-1 text-sm font-medium">
            PPPoE #{p.key} <InterfaceChip name={p.interface} />{" "}
            <span className="text-muted-fg">{p.descr ?? ""}</span>
          </div>
          <Dl
            items={[
              ["Mode", p.mode ?? "—"],
              ["Local IP", p.localip ?? "—"],
              ["Remote IP pool", p.remoteip ?? "—"],
              [
                "RADIUS",
                p.radius_enabled ? (
                  <span className="inline-flex items-center gap-2">
                    <Badge tone="success">enabled</Badge>
                    {p.radius_server ?? ""}
                    {p.radius_secret === "***redacted***" && <Redacted />}
                  </span>
                ) : (
                  "disabled"
                ),
              ],
              [
                "Users",
                p.users.length ? `${p.users.length} account(s)` : "—",
              ],
            ]}
          />
          {p.users.length > 0 && (
            <div className="mt-2">
              <Table
                headers={["Name", "IP", "Password"]}
                rowKeys={p.users.map((u) => u.name)}
                rows={p.users.map((u) => [
                  u.name,
                  u.ip ?? "—",
                  <RV v={u.password} key="pw" />,
                ])}
              />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function EzShaperPanel({ c }: { c: EzShaperConfig }) {
  return (
    <div className="space-y-3">
      <Dl
        items={[
          ["Wizard step", c.step ?? "—"],
          ["Interface", <InterfaceChip key="i" name={c.interface} />],
          ["Upload", c.upload ?? "—"],
          ["Download", c.download ?? "—"],
        ]}
      />
      {c.queues.length > 0 && (
        <div>
          <div className="mb-1 text-xs uppercase text-muted-fg">
            Queues ({c.queues.length})
          </div>
          <Table
            headers={["Name", "Bandwidth", "Unit"]}
            rowKeys={c.queues.map((q) => q.name)}
            rows={c.queues.map((q) => [
              q.name,
              q.bandwidth ?? "—",
              q.bandwidth_unit ?? "—",
            ])}
          />
        </div>
      )}
    </div>
  );
}
