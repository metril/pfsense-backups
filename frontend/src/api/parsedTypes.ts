// Types for the structured config parser + diff, mirroring
// pfsense_shared/pfsense_parser.py and pfsense_shared/pfsense_diff.py.
//
// We keep these deliberately loose (most fields are optional/nullable)
// because older pfSense backups omit lots of tags and the parser
// normalises missing ones to null/[]. Any field that might come back
// as null is typed `| null`.

// ---------- parser ----------

export interface WebGui {
  protocol: string | null;
  port: string | null;
  ssl_certref: string | null;
  disablehttpredirect: boolean;
  loginautocomplete: boolean;
}

export interface SystemInfo {
  hostname: string | null;
  domain: string | null;
  timezone: string | null;
  timeservers: string[];
  language: string | null;
  dnsservers: string[];
  dns_allow_override: boolean;
  dnslocalhost: boolean;
  disablenatreflection: boolean;
  webgui: WebGui | null;
  enablesshd: boolean;
  sshport: string | null;
  powerd_ac_mode: string | null;
  powerd_battery_mode: string | null;
  powerd_normal_mode: string | null;
}

export interface Revision {
  time: string | null;  // ISO datetime from Pydantic
  description: string | null;
  username: string | null;
}

export interface SysctlTunable {
  tunable: string;
  value: string | null;
  descr: string | null;
}

export interface CronJob {
  key: string;
  minute: string | null;
  hour: string | null;
  mday: string | null;
  month: string | null;
  wday: string | null;
  who: string | null;
  command: string | null;
}

export interface Interface {
  key: string;
  descr: string | null;
  if_: string | null;
  enabled: boolean;
  ipaddr: string | null;
  subnet: string | null;
  gateway: string | null;
  ipaddrv6: string | null;
  subnetv6: string | null;
  gatewayv6: string | null;
  mtu: string | null;
  mss: string | null;
  media: string | null;
  mediaopt: string | null;
  blockpriv: boolean;
  blockbogons: boolean;
}

export interface Vlan {
  key: string;
  if_: string | null;
  tag: string | null;
  pcp: string | null;
  vlanif: string | null;
  descr: string | null;
}

export interface Bridge {
  bridgeif: string;
  members: string[];
  descr: string | null;
  enablestp: boolean;
}

export interface Tunnel {
  kind: "gif" | "gre";
  name: string;
  if_: string | null;
  remote_addr: string | null;
  tunnel_local_addr: string | null;
  tunnel_remote_addr: string | null;
  tunnel_remote_net: string | null;
  descr: string | null;
}

export interface Ppp {
  ptpid: string;
  type: string | null;
  if_: string | null;
  username: string | null;
  provider: string | null;
  phone: string | null;
  descr: string | null;
}

export interface QinQ {
  key: string;
  if_: string | null;
  tag: string | null;
  members: string[];
  descr: string | null;
}

export interface WolHost {
  mac: string;
  interface: string | null;
  descr: string | null;
}

export interface VirtualIP {
  key: string;
  mode: string | null;
  interface: string | null;
  subnet: string | null;
  subnet_bits: string | null;
  vhid: string | null;
  advbase: string | null;
  advskew: string | null;
  descr: string | null;
  password: string | null;
}

export interface HaSync {
  pfsyncenabled: boolean;
  pfsyncinterface: string | null;
  pfsyncpeerip: string | null;
  synchronizetoip: string | null;
  username: string | null;
  password: string | null;
  synchronizerules: boolean;
  synchronizenat: boolean;
  synchronizealiases: boolean;
  synchronizeschedules: boolean;
  synchronizedhcpd: boolean;
  synchronizedhcrelay: boolean;
  synchronizedns: boolean;
  synchronizeopenvpn: boolean;
  synchronizeipsec: boolean;
  synchronizeusers: boolean;
  synchronizeauthservers: boolean;
  synchronizecerts: boolean;
}

export interface Gateway {
  name: string;
  interface: string | null;
  gateway: string | null;
  ipprotocol: string | null;
  monitor: string | null;
  descr: string | null;
  weight: string | null;
  defaultgw: boolean;
  disabled: boolean;
}

export interface GatewayGroup {
  name: string;
  descr: string | null;
  trigger: string | null;
  members: string[];
}

export interface StaticRoute {
  key: string;
  network: string | null;
  gateway: string | null;
  descr: string | null;
  disabled: boolean;
}

export interface Endpoint {
  any_: boolean;
  network: string | null;
  address: string | null;
  port: string | null;
  not_: boolean;
}

export interface FirewallRule {
  key: string;
  tracker: string | null;
  type: string | null;
  interface: string | null;
  ipprotocol: string | null;
  protocol: string | null;
  source: Endpoint;
  destination: Endpoint;
  descr: string | null;
  disabled: boolean;
  log: boolean;
  statetype: string | null;
  gateway: string | null;
  schedule: string | null;
  floating: boolean;
}

export interface NatRule {
  key: string;
  kind: "port_forward" | "one_to_one" | "outbound";
  interface: string | null;
  protocol: string | null;
  source: Endpoint;
  destination: Endpoint;
  target: string | null;
  local_port: string | null;
  descr: string | null;
  disabled: boolean;
}

export interface Alias {
  name: string;
  type: string | null;
  descr: string | null;
  entries: string[];
  details: string[];
  updatefreq: string | null;
}

export interface DhcpStaticMap {
  mac: string | null;
  ipaddr: string | null;
  hostname: string | null;
  descr: string | null;
}

export interface DhcpServer {
  interface: string;
  enabled: boolean;
  range_from: string | null;
  range_to: string | null;
  domain: string | null;
  dnsservers: string[];
  gateway: string | null;
  domainsearchlist: string | null;
  static_mappings: DhcpStaticMap[];
}

export interface DnsHostOverride {
  host: string | null;
  domain: string | null;
  ip: string | null;
  descr: string | null;
}

export interface DnsDomainOverride {
  domain: string | null;
  ip: string | null;
  descr: string | null;
}

export interface DnsConfig {
  unbound_enabled: boolean;
  dnsmasq_enabled: boolean;
  unbound_port: string | null;
  dnsmasq_port: string | null;
  host_overrides: DnsHostOverride[];
  domain_overrides: DnsDomainOverride[];
}

export interface User {
  name: string;
  uid: string | null;
  scope: string | null;
  descr: string | null;
  bcrypt_hash: string | null;
  disabled: boolean;
  groups: string[];
  certrefs: string[];
  expires: string | null;
}

export interface Group {
  name: string;
  gid: string | null;
  scope: string | null;
  description: string | null;
  privs: string[];
  members: string[];
}

export interface AuthServer {
  name: string;
  type: string | null;
  host: string | null;
  port: string | null;
  ldap_bindpw: string | null;
  radius_secret: string | null;
  ldap_binddn: string | null;
  ldap_basedn: string | null;
  ldap_scope: string | null;
  ldap_authcn: string | null;
}

export interface RawSection {
  tag: string;
  xml: string;
}

export interface ParsedConfig {
  config_version: string | null;
  system: SystemInfo | null;
  revision: Revision | null;
  sysctl: SysctlTunable[];
  cron: CronJob[];
  interfaces: Interface[];
  vlans: Vlan[];
  bridges: Bridge[];
  gifs: Tunnel[];
  gres: Tunnel[];
  ppps: Ppp[];
  qinqs: QinQ[];
  wol: WolHost[];
  gateways: Gateway[];
  gateway_groups: GatewayGroup[];
  static_routes: StaticRoute[];
  virtual_ips: VirtualIP[];
  hasync: HaSync | null;
  firewall_rules: FirewallRule[];
  nat_rules: NatRule[];
  aliases: Alias[];
  dhcp_servers: DhcpServer[];
  dns: DnsConfig | null;
  users: User[];
  groups: Group[];
  authservers: AuthServer[];
  unrecognized_sections: RawSection[];
}

// ---------- diff ----------

export interface FieldChange {
  field: string;
  before: unknown;
  after: unknown;
}

export interface ItemDiff {
  key: string;
  label: string;
  changes: FieldChange[];
}

export interface ReorderEvent {
  key: string;
  label: string;
  old_index: number;
  new_index: number;
}

export interface SectionDiff {
  added: Record<string, unknown>[];
  removed: Record<string, unknown>[];
  modified: ItemDiff[];
  reordered: ReorderEvent[];
  unchanged_count: number;
}

export interface ConfigDiff {
  system: SectionDiff;
  revision: SectionDiff;
  sysctl: SectionDiff;
  cron: SectionDiff;
  interfaces: SectionDiff;
  vlans: SectionDiff;
  bridges: SectionDiff;
  gifs: SectionDiff;
  gres: SectionDiff;
  ppps: SectionDiff;
  qinqs: SectionDiff;
  wol: SectionDiff;
  gateways: SectionDiff;
  gateway_groups: SectionDiff;
  static_routes: SectionDiff;
  virtual_ips: SectionDiff;
  hasync: SectionDiff;
  firewall_rules: SectionDiff;
  nat_rules: SectionDiff;
  aliases: SectionDiff;
  dhcp_servers: SectionDiff;
  dns: SectionDiff;
  users: SectionDiff;
  groups: SectionDiff;
  authservers: SectionDiff;
  unrecognized_sections: SectionDiff;
  config_version: SectionDiff;
}
