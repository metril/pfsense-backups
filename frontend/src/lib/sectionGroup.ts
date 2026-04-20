/**
 * Maps each ParsedConfig section to one of six functional groups. The
 * group determines the left-stripe color + title hue on the section
 * card in ParsedBackupView and the colored summary chip in
 * ParsedBackupDiff. Keep this list in sync with the section list in
 * `frontend/src/api/parsedTypes.ts` — an unlisted section falls through
 * to "neutral".
 */

export type SectionGroup =
  | "system"
  | "networking"
  | "security"
  | "services"
  | "vpn-pki"
  | "packages"
  | "neutral";

/** Sections that belong to each group. Keys are the field name on
 *  ParsedConfig / the TS key in ConfigDiff — they must match one-to-one
 *  or the color mapping silently disappears. */
const GROUP_MEMBERS: Record<Exclude<SectionGroup, "neutral">, string[]> = {
  system: [
    "system",
    "revision",
    "sysctl",
    "cron",
    "notifications",
    // ``config_version`` is a scalar header but it belongs to the
    // system group — operators reading the diff expect a pfSense
    // config-version bump next to revision changes.
    "config_version",
  ],
  networking: [
    "interfaces",
    "vlans",
    "bridges",
    "gifs",
    "gres",
    "ppps",
    "qinqs",
    "laggs",
    "wol",
    "gateways",
    "gateway_groups",
    "static_routes",
    "virtual_ips",
    "hasync",
    "igmpproxy_entries",
    "radvd_interfaces",
  ],
  security: ["firewall_rules", "nat_rules", "aliases", "schedules"],
  services: [
    "dhcp_servers",
    "dhcp_relays",
    "dns",
    "ntpd",
    "snmpd",
    "syslog",
    "shaper_queues",
    "dnshaper_pipes",
    "lb_pools",
    "lb_virtual_servers",
    "captive_portal_zones",
    "dyndns_entries",
    "ups",
    "voucher_rolls",
    "ftpproxy",
  ],
  "vpn-pki": [
    "openvpn_servers",
    "openvpn_clients",
    "openvpn_cscs",
    "ipsec_phase1",
    "ipsec_phase2",
    "ipsec_psks",
    "certificate_authorities",
    "certificates",
    "crls",
    "users",
    "groups",
    "authservers",
  ],
  packages: ["installedpackages"],
};

const KEY_TO_GROUP: Record<string, SectionGroup> = (() => {
  const m: Record<string, SectionGroup> = {};
  for (const [g, keys] of Object.entries(GROUP_MEMBERS)) {
    for (const k of keys) m[k] = g as SectionGroup;
  }
  return m;
})();

export function sectionGroup(key: string): SectionGroup {
  return KEY_TO_GROUP[key] ?? "neutral";
}

/** Resolves a group to its Tailwind class names. Keeping these in one
 *  place means a palette tweak only touches this file. */
export interface GroupClasses {
  /** Border stripe on the section card */
  stripe: string;
  /** Title text color */
  title: string;
  /** Subtle tinted background for chips that carry this group color */
  chipBg: string;
  /** Border for chips */
  chipBorder: string;
}

export function groupClasses(g: SectionGroup): GroupClasses {
  switch (g) {
    case "system":
      return {
        stripe: "border-l-group-system",
        title: "text-group-system",
        chipBg: "bg-group-system/10",
        chipBorder: "border-group-system/40",
      };
    case "networking":
      return {
        stripe: "border-l-group-net",
        title: "text-group-net",
        chipBg: "bg-group-net/10",
        chipBorder: "border-group-net/40",
      };
    case "security":
      return {
        stripe: "border-l-group-security",
        title: "text-group-security",
        chipBg: "bg-group-security/10",
        chipBorder: "border-group-security/40",
      };
    case "services":
      return {
        stripe: "border-l-group-services",
        title: "text-group-services",
        chipBg: "bg-group-services/10",
        chipBorder: "border-group-services/40",
      };
    case "vpn-pki":
      return {
        stripe: "border-l-group-vpn",
        title: "text-group-vpn",
        chipBg: "bg-group-vpn/10",
        chipBorder: "border-group-vpn/40",
      };
    case "packages":
      return {
        stripe: "border-l-group-packages",
        title: "text-group-packages",
        chipBg: "bg-group-packages/10",
        chipBorder: "border-group-packages/40",
      };
    default:
      return {
        stripe: "border-l-border",
        title: "text-fg",
        chipBg: "bg-muted/30",
        chipBorder: "border-border",
      };
  }
}
