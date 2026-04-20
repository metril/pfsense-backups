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

export interface Lagg {
  laggif: string;
  members: string[];
  proto: string | null;
  lacptimeout: string | null;
  lacp_fast_timeout: boolean;
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

export interface NtpdConfig {
  enable: boolean;
  interfaces: string[];
  timeservers: string[];
  orphan: string | null;
  leapsec: string | null;
}

export interface SnmpdConfig {
  enable: boolean;
  syslocation: string | null;
  syscontact: string | null;
  rocommunity: string | null;
  rwcommunity: string | null;
  pollport: string | null;
  trapenable: boolean;
  trapserver: string | null;
  trapserverport: string | null;
  trapstring: string | null;
  bindlan: boolean;
  bindip: string | null;
}

export interface SyslogHost {
  key: string;
  host: string;
  sourceip: string | null;
  ipprotocol: string | null;
}

export interface SyslogConfig {
  enable: boolean;
  reverse: boolean;
  nentries: string | null;
  filter_: boolean;
  dhcp: boolean;
  portalauth: boolean;
  vpn: boolean;
  dpinger: boolean;
  hostapd: boolean;
  system: boolean;
  resolver: boolean;
  ppp: boolean;
  routing: boolean;
  ntpd: boolean;
  hosts: SyslogHost[];
}

export interface DhcpRelayConfig {
  kind: "ipv4" | "ipv6";
  enable: boolean;
  interface: string[];
  server: string[];
  agentoption: boolean;
}

export interface Schedule {
  name: string;
  descr: string | null;
  time_ranges: string[];
}

export interface ShaperQueue {
  name: string;
  interface: string | null;
  priority: string | null;
  bandwidth: string | null;
  bandwidthtype: string | null;
  descr: string | null;
}

export interface DnShaperPipe {
  name: string;
  number: string | null;
  bandwidth: string | null;
  bandwidthtype: string | null;
  descr: string | null;
}

export interface LoadBalancerPoolMember {
  ip: string | null;
  port: string | null;
}

export interface LoadBalancerPool {
  name: string;
  descr: string | null;
  behaviour: string | null;
  port: string | null;
  monitor: string | null;
  servers: LoadBalancerPoolMember[];
}

export interface LoadBalancerVirtualServer {
  name: string;
  descr: string | null;
  ipaddr: string | null;
  port: string | null;
  mode: string | null;
  poolname: string | null;
}

export interface CaptivePortalZone {
  zone: string;
  zoneid: string | null;
  enable: boolean;
  interfaces: string[];
  auth_method: string | null;
  redirurl: string | null;
  radius_secret: string | null;
}

export interface DyndnsEntry {
  key: string;
  type: string | null;
  interface: string | null;
  host: string | null;
  domainname: string | null;
  mx: string | null;
  descr: string | null;
  enabled: boolean;
  wildcard: boolean;
  force_update: boolean;
  verboselog: boolean;
  username: string | null;
  password: string | null;
  token: string | null;
}

export interface SmtpNotifier {
  enabled: boolean;
  ipaddress: string | null;
  port: string | null;
  timeout: string | null;
  ssl: boolean;
  sslvalidate: boolean;
  fromaddress: string | null;
  notifyemailaddress: string | null;
  authentication_mechanism: string | null;
  username: string | null;
  password: string | null;
}

export interface PushoverNotifier {
  enabled: boolean;
  api_key: string | null;
  user_key: string | null;
}

export interface GrowlNotifier {
  enabled: boolean;
  name: string | null;
  notification_name: string | null;
  ipaddress: string | null;
  password: string | null;
}

export interface TelegramNotifier {
  enabled: boolean;
  chat_id: string | null;
  api_token: string | null;
}

export interface SlackNotifier {
  enabled: boolean;
  webhook_url: string | null;
}

export interface NotificationConfig {
  smtp: SmtpNotifier | null;
  pushover: PushoverNotifier | null;
  growl: GrowlNotifier | null;
  telegram: TelegramNotifier | null;
  slack: SlackNotifier | null;
}

export interface IgmpProxyEntry {
  key: string;
  type: string | null;
  ifname: string | null;
  descr: string | null;
  threshold: string | null;
  networks: string[];
}

export interface RadvdInterfaceConfig {
  interface: string;
  ramode: string | null;
  rapriority: string | null;
  ramininterval: string | null;
  ramaxinterval: string | null;
  ralifetime: string | null;
  radomainsearchlist: string | null;
  radns: string[];
}

export interface UpsConfig {
  enable: boolean;
  driver: string | null;
  port: string | null;
  cable: string | null;
  upsname: string | null;
  remoteuser: string | null;
  remotepassword: string | null;
}

export interface VoucherRoll {
  number: string;
  minutes: string | null;
  count: string | null;
  descr: string | null;
}

export interface FtpProxyConfig {
  enable: boolean;
  ports: string | null;
  interface: string | null;
}

export interface OpenVpnServer {
  vpnid: string;
  description: string | null;
  mode: string | null;
  protocol: string | null;
  interface: string | null;
  local_port: string | null;
  tunnel_network: string | null;
  tunnel_networkv6: string | null;
  remote_network: string | null;
  remote_networkv6: string | null;
  local_network: string | null;
  local_networkv6: string | null;
  dev_mode: string | null;
  topology: string | null;
  crypto: string | null;
  digest: string | null;
  caref: string | null;
  certref: string | null;
  authmode: string[];
  shared_key: string | null;
  tls: string | null;
}

export interface OpenVpnClient {
  vpnid: string;
  description: string | null;
  mode: string | null;
  protocol: string | null;
  interface: string | null;
  server_addr: string | null;
  server_port: string | null;
  tunnel_network: string | null;
  dev_mode: string | null;
  crypto: string | null;
  digest: string | null;
  caref: string | null;
  certref: string | null;
  shared_key: string | null;
  tls: string | null;
}

export interface OpenVpnCsc {
  common_name: string;
  description: string | null;
  disable: boolean;
  block: boolean;
  server_list: string[];
  tunnel_network: string | null;
  local_network: string | null;
  remote_network: string | null;
  push_reset: boolean;
  dns_server1: string | null;
  ntp_server1: string | null;
}

export interface IpsecPhase1 {
  ikeid: string;
  iketype: string | null;
  interface: string | null;
  remote_gateway: string | null;
  protocol: string | null;
  descr: string | null;
  disabled: boolean;
  authentication_method: string | null;
  myid_type: string | null;
  myid_data: string | null;
  peerid_type: string | null;
  peerid_data: string | null;
  pre_shared_key: string | null;
  encryption_set: string[];
}

export interface IpsecPhase2 {
  uniqid: string;
  ikeid: string | null;
  descr: string | null;
  disabled: boolean;
  mode: string | null;
  protocol: string | null;
  local_type: string | null;
  local_address: string | null;
  local_netbits: string | null;
  remote_type: string | null;
  remote_address: string | null;
  remote_netbits: string | null;
  encryption_set: string[];
}

export interface IpsecPskEntry {
  key: string;
  ident_type: string | null;
  ident: string | null;
  pre_shared_key: string | null;
}

export interface CertMetadata {
  subject_cn: string | null;
  subject: string | null;
  issuer_cn: string | null;
  issuer: string | null;
  serial_hex: string | null;
  not_before: string | null;
  not_after: string | null;
  sans: string[];
  fingerprint_sha256: string | null;
}

export interface CertificateAuthority {
  refid: string;
  descr: string | null;
  crt: string | null;
  prv: string | null;
  serial: string | null;
  metadata: CertMetadata | null;
}

export interface Certificate {
  refid: string;
  descr: string | null;
  caref: string | null;
  type: string | null;
  crt: string | null;
  prv: string | null;
  metadata: CertMetadata | null;
}

export interface CertificateRevocationList {
  refid: string;
  descr: string | null;
  caref: string | null;
  method: string | null;
  lifetime: string | null;
  serial: string | null;
  revoked_cert_refids: string[];
  text: string | null;
}

// ----- installedpackages -----

export interface PfBlockerNgFeed {
  key: string;
  header: string | null;
  state: string | null;
  format: string | null;
  action: string | null;
  url: string | null;
}

export interface PfBlockerNgConfig {
  enable_pfblockerng: boolean;
  keep_settings: boolean;
  pfb_interface: string | null;
  pfb_inbound: string | null;
  pfb_outbound: string | null;
  ip_enabled: boolean;
  ipv6_enabled: boolean;
  maxmind_key_configured: boolean;
  dnsbl_enabled: boolean;
  dnsbl_mode: string | null;
  dnsbl_port: string | null;
  feeds: PfBlockerNgFeed[];
  topspammers_present: boolean;
  blacklist_present: boolean;
  safesearch_present: boolean;
  reputation_present: boolean;
  dnsbl_safesearch_present: boolean;
  global_present: boolean;
}

export interface HaProxyFrontend {
  name: string;
  status: string | null;
  type: string | null;
  descr: string | null;
  extaddr: string | null;
  addresses: string[];
  default_backend: string | null;
  ssl: boolean;
  forwardfor: boolean;
}

export interface HaProxyServer {
  name: string;
  address: string | null;
  port: string | null;
  ssl: boolean;
  status: string | null;
  weight: string | null;
  password: string | null;
}

export interface HaProxyBackend {
  name: string;
  descr: string | null;
  balance: string | null;
  check_type: string | null;
  servers: HaProxyServer[];
}

export interface HaProxyConfig {
  enable: boolean;
  advanced: string | null;
  remotesyslog: string | null;
  frontends: HaProxyFrontend[];
  backends: HaProxyBackend[];
}

export interface SuricataInterface {
  uuid: string;
  interface: string | null;
  descr: string | null;
  enable: boolean;
  blockoffenders7: boolean;
  ips_mode: string | null;
  eve_enable: boolean;
  categories: string[];
}

export interface SuricataPasslistEntry {
  key: string;
  address: string | null;
  descr: string | null;
}

export interface SuricataPasslist {
  name: string;
  descr: string | null;
  entries: SuricataPasslistEntry[];
}

export interface SuricataConfig {
  enable_stats: boolean;
  oinkmaster_configured: boolean;
  interfaces: SuricataInterface[];
  passlists: SuricataPasslist[];
}

export interface AcmeAccountKey {
  name: string;
  descr: string | null;
  acmeserver: string | null;
  email: string | null;
  accountkey: string | null;
}

export interface AcmeCertificate {
  name: string;
  acmeaccount: string | null;
  keylength: string | null;
  preferredchain: string | null;
  ocspstaple: boolean;
  dnssleep: string | null;
  san_list: string[];
  renewafter: string | null;
}

export interface AcmeConfig {
  enable: boolean;
  writecert_log: boolean;
  account_keys: AcmeAccountKey[];
  certificates: AcmeCertificate[];
}

// --- v0.12.0 package types ---

export interface SquidConfig {
  enable: boolean;
  active_interface: string | null;
  proxy_port: string | null;
  transparent_mode: boolean;
  allow_interface: string[];
  auth_method: string | null;
  auth_realm: string | null;
  ldap_server: string | null;
  ldap_binddn: string | null;
  ldap_bindpw: string | null;
  ntlm_domain: string | null;
  ntlm_admin_username: string | null;
  ntlm_admin_password: string | null;
}

export interface SquidGuardTarget {
  name: string;
  descr: string | null;
  domain_list: string[];
  url_list: string[];
  enabled: boolean;
}

export interface SquidGuardAcl {
  name: string;
  descr: string | null;
  source: string | null;
  time_range: string | null;
  redirect: string | null;
  enabled: boolean;
}

export interface SquidGuardConfig {
  enabled: boolean;
  blacklist_enabled: boolean;
  blacklist_url: string | null;
  strip_path: boolean;
  targets: SquidGuardTarget[];
  acls: SquidGuardAcl[];
}

export interface SquidAuthConfig {
  auth_method: string | null;
  ldap_server: string | null;
  ldap_port: string | null;
  ldap_binddn: string | null;
  ldap_pass: string | null;
  ldap_search_base: string | null;
  ldap_filter: string | null;
  radius_server: string | null;
  radius_port: string | null;
  radius_secret: string | null;
}

export interface SquidBundle {
  squid: SquidConfig | null;
  squidguard: SquidGuardConfig | null;
  cache_present: boolean;
  remote_present: boolean;
  auth: SquidAuthConfig | null;
  antivirus_present: boolean;
}

export interface FreeRadiusClient {
  name: string;
  ipaddr: string | null;
  shortname: string | null;
  shared_secret: string | null;
  nas_type: string | null;
  descr: string | null;
}

export interface FreeRadiusUser {
  name: string;
  password: string | null;
  auth_type: string | null;
  expiration: string | null;
  descr: string | null;
}

export interface FreeRadiusInterface {
  key: string;
  ipaddr: string | null;
  port: string | null;
  ip_type: string | null;
  interface_type: string | null;
}

export interface FreeRadiusConfig {
  enabled: boolean;
  interfaces: FreeRadiusInterface[];
  clients: FreeRadiusClient[];
  users: FreeRadiusUser[];
}

export interface TelegrafConfig {
  enabled: boolean;
  interval: string | null;
  output_plugin: string | null;
  url: string | null;
  database: string | null;
  organization: string | null;
  bucket: string | null;
  username: string | null;
  password: string | null;
  token: string | null;
}

export interface FrrBgpNeighbor {
  name: string;
  remote_as: string | null;
  peer_address: string | null;
  descr: string | null;
  password: string | null;
}

export interface FrrBgpConfig {
  enabled: boolean;
  local_as: string | null;
  router_id: string | null;
  neighbors: FrrBgpNeighbor[];
}

export interface FrrOspfInterface {
  interface: string;
  area: string | null;
  cost: string | null;
  priority: string | null;
  hello_interval: string | null;
  dead_interval: string | null;
  md5_password: string | null;
}

export interface FrrOspfConfig {
  enabled: boolean;
  router_id: string | null;
  interfaces: FrrOspfInterface[];
}

export interface FrrOspfdInterface {
  interface: string;
  area: string | null;
  cost: string | null;
  priority: string | null;
  hello_interval: string | null;
  dead_interval: string | null;
  md5_password: string | null;
}

export interface FrrConfig {
  enabled: boolean;
  bgp: FrrBgpConfig | null;
  ospf: FrrOspfConfig | null;
  ospfd_present: boolean;
  ospfd_areas_present: boolean;
  ospfd_interfaces_present: boolean;
  global_acls_present: boolean;
  global_prefixes_present: boolean;
  ospfd_interfaces: FrrOspfdInterface[];
}

export interface ZabbixAgentConfig {
  enabled: boolean;
  server: string | null;
  serveractive: string | null;
  hostname: string | null;
  listenport: string | null;
  tls_psk_identity: string | null;
  tls_psk: string | null;
}

export interface ZabbixProxyConfig {
  enabled: boolean;
  server: string | null;
  hostname: string | null;
  listenport: string | null;
  tls_psk_identity: string | null;
  tls_psk: string | null;
}

export interface ZabbixBundle {
  agent: ZabbixAgentConfig | null;
  proxy: ZabbixProxyConfig | null;
}

export interface UnknownPackage {
  tag: string;
  entry_count: number;
  xml: string;
}

export interface WireGuardTunnel {
  name: string;
  descr: string | null;
  enabled: boolean;
  listen_port: string | null;
  mtu: string | null;
  addresses: string[];
  public_key: string | null;
  private_key: string | null;
}

export interface WireGuardPeer {
  descr: string | null;
  enabled: boolean;
  tun: string | null;
  endpoint: string | null;
  port: string | null;
  persistent_keepalive: string | null;
  allowed_ips: string[];
  public_key: string | null;
  preshared_key: string | null;
}

export interface WireGuardConfig {
  tunnels: WireGuardTunnel[];
  peers: WireGuardPeer[];
}

export interface SnortInterface {
  uuid: string;
  interface: string | null;
  descr: string | null;
  enable: boolean;
  blockoffenders: boolean;
  ips_mode: string | null;
  categories: string[];
}

export interface SnortConfig {
  oinkmaster_configured: boolean;
  snort_community_rules_enabled: boolean;
  emerging_threats_enabled: boolean;
  interfaces: SnortInterface[];
}

export interface MiniUpnpdConfig {
  enable: boolean;
  enable_upnp: boolean;
  enable_natpmp: boolean;
  iface_array: string | null;
  ext_iface: string | null;
  download: string | null;
  upload: string | null;
  permit_rules: string[];
}

export interface AvahiConfig {
  enable: boolean;
  reflector: boolean;
  ipv4_only: boolean;
  ipv6_only: boolean;
  interfaces: string | null;
  allow_deny_interfaces: string | null;
  cache_entries_max: string | null;
}

export interface OpenvpnClientExportConfig {
  use_random_local_port: boolean;
  silent_install: boolean;
  interface_selection: string | null;
  hostname: string | null;
  ovpnexportcert: string | null;
  ovpnexportcountry: string | null;
  ovpnexportstate: string | null;
  ovpnexportcity: string | null;
}

export interface ShellCmdEntry {
  cmd: string;
  cmdtype: string | null;
  descr: string | null;
  disabled: boolean;
}

export interface ShellCmdSettings {
  entries: ShellCmdEntry[];
}

export interface InstalledPackages {
  pfblockerng: PfBlockerNgConfig | null;
  haproxy: HaProxyConfig | null;
  suricata: SuricataConfig | null;
  acme: AcmeConfig | null;
  squid: SquidBundle | null;
  freeradius: FreeRadiusConfig | null;
  telegraf: TelegrafConfig | null;
  frr: FrrConfig | null;
  zabbix: ZabbixBundle | null;
  wireguard: WireGuardConfig | null;
  snort: SnortConfig | null;
  miniupnpd: MiniUpnpdConfig | null;
  avahi: AvahiConfig | null;
  openvpn_client_export: OpenvpnClientExportConfig | null;
  shellcmd: ShellCmdSettings | null;
  unknown: UnknownPackage[];
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

// ----- v0.14.0: previously-unrecognised tags now structured -----

export interface SshHostKeyFile {
  filename: string;
  is_private: boolean;
  xmldata: string | null;
}

export interface SshData {
  keys: SshHostKeyFile[];
}

export interface LastChange {
  time: string | null;
  username: string | null;
}

export interface ThemePreference {
  name: string | null;
}

export interface DiagPreferences {
  ipv6nat: boolean;
  shownoaliases: boolean;
  showallpasswords: boolean;
}

export interface DhcpBackend {
  backend: string | null;
}

export interface LegacyBridge {
  enabled: boolean;
  interfaces: string[];
}

export interface ProxyArpEntry {
  key: string;
  interface: string | null;
  network: string | null;
  descr: string | null;
}

export interface InterfaceGroup {
  ifname: string;
  members: string[];
  descr: string | null;
}

export interface EzShaperQueue {
  name: string;
  bandwidth: string | null;
  bandwidth_unit: string | null;
}

export interface EzShaperConfig {
  step: string | null;
  interface: string | null;
  upload: string | null;
  download: string | null;
  queues: EzShaperQueue[];
}

export interface OvpnServerWizard {
  step: string | null;
  description: string | null;
  cacrt: string | null;
  cakey: string | null;
  crt: string | null;
  key: string | null;
}

export interface ApiKeyEntry {
  key: string;
  username: string | null;
  descr: string | null;
  apikey: string | null;
  apisecret: string | null;
}

export interface L2tpUser {
  name: string;
  ip: string | null;
  password: string | null;
}

export interface L2tpConfig {
  mode: string | null;
  interface: string | null;
  localip: string | null;
  remoteip: string | null;
  radius_enabled: boolean;
  radius_server: string | null;
  radius_secret: string | null;
  users: L2tpUser[];
}

export interface PppoeUser {
  name: string;
  ip: string | null;
  password: string | null;
}

export interface PppoeServerEntry {
  key: string;
  mode: string | null;
  interface: string | null;
  localip: string | null;
  remoteip: string | null;
  descr: string | null;
  radius_enabled: boolean;
  radius_server: string | null;
  radius_secret: string | null;
  users: PppoeUser[];
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
  laggs: Lagg[];
  wol: WolHost[];
  gateways: Gateway[];
  gateway_groups: GatewayGroup[];
  static_routes: StaticRoute[];
  virtual_ips: VirtualIP[];
  hasync: HaSync | null;
  firewall_rules: FirewallRule[];
  nat_rules: NatRule[];
  aliases: Alias[];
  dyndns_entries: DyndnsEntry[];
  notifications: NotificationConfig | null;
  dhcp_servers: DhcpServer[];
  dhcp_relays: DhcpRelayConfig[];
  dns: DnsConfig | null;
  ntpd: NtpdConfig | null;
  snmpd: SnmpdConfig | null;
  syslog: SyslogConfig | null;
  schedules: Schedule[];
  shaper_queues: ShaperQueue[];
  dnshaper_pipes: DnShaperPipe[];
  lb_pools: LoadBalancerPool[];
  lb_virtual_servers: LoadBalancerVirtualServer[];
  captive_portal_zones: CaptivePortalZone[];
  igmpproxy_entries: IgmpProxyEntry[];
  radvd_interfaces: RadvdInterfaceConfig[];
  ups: UpsConfig | null;
  voucher_rolls: VoucherRoll[];
  ftpproxy: FtpProxyConfig | null;
  openvpn_servers: OpenVpnServer[];
  openvpn_clients: OpenVpnClient[];
  openvpn_cscs: OpenVpnCsc[];
  ipsec_phase1: IpsecPhase1[];
  ipsec_phase2: IpsecPhase2[];
  ipsec_psks: IpsecPskEntry[];
  certificate_authorities: CertificateAuthority[];
  certificates: Certificate[];
  crls: CertificateRevocationList[];
  users: User[];
  groups: Group[];
  authservers: AuthServer[];
  // v0.14.0 additions
  sshdata: SshData | null;
  lastchange: LastChange | null;
  theme: ThemePreference | null;
  diag: DiagPreferences | null;
  dhcp_backend: DhcpBackend | null;
  legacy_bridge: LegacyBridge | null;
  proxyarp: ProxyArpEntry[];
  interface_groups: InterfaceGroup[];
  ezshaper: EzShaperConfig | null;
  ovpnserver_wizard: OvpnServerWizard | null;
  apikeys: ApiKeyEntry[];
  l2tp: L2tpConfig | null;
  pppoe_servers: PppoeServerEntry[];
  installedpackages: InstalledPackages | null;
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
  laggs: SectionDiff;
  wol: SectionDiff;
  gateways: SectionDiff;
  gateway_groups: SectionDiff;
  static_routes: SectionDiff;
  virtual_ips: SectionDiff;
  hasync: SectionDiff;
  firewall_rules: SectionDiff;
  nat_rules: SectionDiff;
  aliases: SectionDiff;
  dyndns_entries: SectionDiff;
  notifications: SectionDiff;
  dhcp_servers: SectionDiff;
  dhcp_relays: SectionDiff;
  dns: SectionDiff;
  ntpd: SectionDiff;
  snmpd: SectionDiff;
  syslog: SectionDiff;
  schedules: SectionDiff;
  shaper_queues: SectionDiff;
  dnshaper_pipes: SectionDiff;
  lb_pools: SectionDiff;
  lb_virtual_servers: SectionDiff;
  captive_portal_zones: SectionDiff;
  igmpproxy_entries: SectionDiff;
  radvd_interfaces: SectionDiff;
  ups: SectionDiff;
  voucher_rolls: SectionDiff;
  ftpproxy: SectionDiff;
  openvpn_servers: SectionDiff;
  openvpn_clients: SectionDiff;
  openvpn_cscs: SectionDiff;
  ipsec_phase1: SectionDiff;
  ipsec_phase2: SectionDiff;
  ipsec_psks: SectionDiff;
  certificate_authorities: SectionDiff;
  certificates: SectionDiff;
  crls: SectionDiff;
  installedpackages: SectionDiff;
  users: SectionDiff;
  groups: SectionDiff;
  authservers: SectionDiff;
  // v0.14.0 additions
  sshdata: SectionDiff;
  lastchange: SectionDiff;
  theme: SectionDiff;
  diag: SectionDiff;
  dhcp_backend: SectionDiff;
  legacy_bridge: SectionDiff;
  proxyarp: SectionDiff;
  interface_groups: SectionDiff;
  ezshaper: SectionDiff;
  ovpnserver_wizard: SectionDiff;
  apikeys: SectionDiff;
  l2tp: SectionDiff;
  pppoe_servers: SectionDiff;
  unrecognized_sections: SectionDiff;
  config_version: SectionDiff;
}
