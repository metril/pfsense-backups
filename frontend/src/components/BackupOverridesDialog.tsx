import { useRef, useState } from "react";
import { AlertTriangle, KeyRound, Package } from "lucide-react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Select, type SelectOption } from "@/components/ui/Select";
import type { BackupOverridesRequest } from "@/api/types";

// Canonical pfSense subsystem IDs for the Area dropdown. Must stay in
// sync with pfsense_shared/schemas.py::PFSENSE_BACKUP_AREAS.
//
// Radix Select reserves value="" for "no selection, show placeholder"
// and throws synchronously on <Select.Item value="">. We use the
// AREA_ALL sentinel inside the UI and translate back to "" at the
// boundary where we build the overrides payload.
const AREA_ALL = "__all__";
const PFSENSE_BACKUP_AREAS: SelectOption[] = [
  { value: AREA_ALL, label: "Everything (default)" },
  { value: "aliases", label: "aliases" },
  { value: "captiveportal", label: "captiveportal" },
  { value: "certs", label: "certs" },
  { value: "cron", label: "cron" },
  { value: "dhcpd", label: "dhcpd" },
  { value: "dhcpdv6", label: "dhcpdv6" },
  { value: "dnsmasq", label: "dnsmasq" },
  { value: "filter", label: "filter (firewall rules)" },
  { value: "firewallshaper", label: "firewallshaper" },
  { value: "ifgroups", label: "ifgroups" },
  { value: "installedpackages", label: "installedpackages" },
  { value: "interfaces", label: "interfaces" },
  { value: "ipsec", label: "ipsec" },
  { value: "load_balancer", label: "load_balancer" },
  { value: "nat", label: "nat" },
  { value: "openvpn", label: "openvpn" },
  { value: "ppps", label: "ppps" },
  { value: "rrddata", label: "rrddata" },
  { value: "schedules", label: "schedules" },
  { value: "snmpd", label: "snmpd" },
  { value: "staticroutes", label: "staticroutes" },
  { value: "syslog", label: "syslog" },
  { value: "sysctl", label: "sysctl" },
  { value: "system", label: "system" },
  { value: "system_advanced_admin", label: "system_advanced_admin" },
  { value: "system_advanced_firewall", label: "system_advanced_firewall" },
  { value: "system_advanced_misc", label: "system_advanced_misc" },
  { value: "system_advanced_network", label: "system_advanced_network" },
  { value: "system_advanced_notifications", label: "system_advanced_notifications" },
  { value: "system_advanced_sysctl", label: "system_advanced_sysctl" },
  { value: "system_hasync", label: "system_hasync" },
  { value: "unbound", label: "unbound" },
  { value: "virtualip", label: "virtualip" },
  { value: "voucher", label: "voucher" },
  { value: "vpn", label: "vpn" },
  { value: "wol", label: "wol" },
];

/**
 * One-shot "Backup now with options" dialog used by:
 *   - per-instance "Backup now" menu item (Dashboard tile, Instance Detail)
 *   - top-bar "Backup all" menu item (Dashboard)
 *
 * Two actions: "Run with stored defaults" (sends no overrides) and
 * "Run with these options" (sends the diff as an overrides payload).
 *
 * Laid out vertically in three tinted sections — Area, Contents,
 * Encryption — so each decision is easy to scan without the
 * 2-column asymmetry that v0.9.x shipped with.
 */
export function BackupOverridesDialog({
  title,
  mode,
  onClose,
  onRun,
}: {
  title: string;
  mode: "single" | "all";
  onClose: () => void;
  onRun: (overrides?: BackupOverridesRequest) => Promise<void>;
}) {
  const [area, setArea] = useState<string>(AREA_ALL);
  const [rrd, setRrd] = useState<boolean>(false);
  const [packages, setPackages] = useState<boolean>(true);
  const [ssh, setSsh] = useState<boolean>(true);
  const [encrypt, setEncrypt] = useState<boolean>(false);
  const [pw, setPw] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const inFlight = useRef(false);

  const passwordMissing = encrypt && pw.trim().length === 0;

  async function run(withOverrides: boolean) {
    if (inFlight.current) return;
    setErr(null);
    if (withOverrides && passwordMissing) {
      setErr("Password required when encryption is on.");
      return;
    }
    inFlight.current = true;
    setSubmitting(true);
    try {
      if (!withOverrides) {
        await onRun(undefined);
      } else {
        const overrides: BackupOverridesRequest = {
          backup_area: area === AREA_ALL ? "" : area,
          backup_include_rrd: rrd,
          backup_include_packages: packages,
          backup_include_ssh: ssh,
          backup_encrypt: encrypt,
        };
        if (encrypt) overrides.backup_encrypt_password = pw;
        await onRun(overrides);
      }
      onClose();
    } catch (e) {
      setErr(String(e));
    } finally {
      setSubmitting(false);
      inFlight.current = false;
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={title}>
      <div className="space-y-4">
        <p className="text-sm text-muted-fg">
          These settings apply only to this run and are not saved back to
          {mode === "all" ? " any instance" : " this instance"}.
        </p>

        <Section
          icon={<Package className="h-4 w-4" aria-hidden />}
          title="Area"
          hint="What subset of pfSense's config to pull. Default is everything."
        >
          <Select
            value={area}
            onChange={setArea}
            options={PFSENSE_BACKUP_AREAS}
            aria-label="Backup area"
          />
        </Section>

        <Section
          icon={<Package className="h-4 w-4" aria-hidden />}
          title="Contents"
          hint="Optional extras pfSense will include in the backup."
        >
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Toggle label="Include RRD graph data" checked={rrd} onChange={setRrd} />
            <Toggle
              label="Include package information"
              checked={packages}
              onChange={setPackages}
            />
            <Toggle label="Include SSH host keys" checked={ssh} onChange={setSsh} />
          </div>
        </Section>

        <Section
          icon={<KeyRound className="h-4 w-4" aria-hidden />}
          title="Encryption"
          hint="Encrypt the config file with AES-256-CBC. pfSense's Restore flow accepts the output directly."
        >
          <Toggle label="Encrypt backup" checked={encrypt} onChange={setEncrypt} />
          {encrypt && (
            <div className="mt-3">
              <Label>Encryption password (one-shot)</Label>
              <Input
                type="password"
                value={pw}
                onChange={(e) => setPw(e.target.value)}
                autoFocus
                className="mt-1"
              />
            </div>
          )}
        </Section>

        {mode === "all" && (
          <div className="flex items-start gap-2 rounded-md border border-warn/30 bg-warn/10 px-3 py-2 text-xs text-fg">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden />
            <div>
              <strong>Heads-up:</strong> these settings apply to every enabled instance.
              If an instance doesn't support the selected area (e.g. a package not installed
              on that box), its backup will fail and show up in the sweep's failed list.
              A shared encryption password will apply to every encrypted backup produced
              by this run.
            </div>
          </div>
        )}

        {err && <p className="text-xs text-danger">{err}</p>}
      </div>

      <div className="mt-6 flex items-center justify-between gap-2">
        <Button variant="secondary" onClick={() => run(false)} disabled={submitting}>
          Run with stored defaults
        </Button>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => run(true)} disabled={submitting || passwordMissing}>
            {submitting ? "Starting…" : "Run with these options"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function Section({
  icon,
  title,
  hint,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-border bg-muted/30 p-4">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-fg">
        <span className="text-fg">{icon}</span>
        {title}
      </div>
      {hint && <p className="mb-3 text-xs text-muted-fg">{hint}</p>}
      {children}
    </section>
  );
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 cursor-pointer accent-accent"
      />
      <span>{label}</span>
    </label>
  );
}
