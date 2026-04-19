import { useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import type { BackupOverridesRequest } from "@/api/types";

// Canonical pfSense subsystem IDs for the Area dropdown. Must stay in
// sync with pfsense_shared/schemas.py::PFSENSE_BACKUP_AREAS.
const PFSENSE_BACKUP_AREAS: { value: string; label: string }[] = [
  { value: "", label: "Everything (default)" },
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
 *   - per-instance "Backup now" gear button (Dashboard tile, Instance Detail)
 *   - top-bar "Backup all" gear button (Dashboard)
 *
 * Two actions: "Run with stored defaults" (sends no overrides) and
 * "Run with these options" (sends the diff as an overrides payload).
 *
 * When `mode === "all"`, the dialog shows the caveat about per-instance
 * area mismatches + shared password effects across every box.
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
  const [area, setArea] = useState<string>("");
  const [rrd, setRrd] = useState<boolean>(false);
  const [packages, setPackages] = useState<boolean>(true);
  const [ssh, setSsh] = useState<boolean>(true);
  const [encrypt, setEncrypt] = useState<boolean>(false);
  const [pw, setPw] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const passwordMissing = encrypt && pw.trim().length === 0;

  async function run(withOverrides: boolean) {
    setErr(null);
    if (withOverrides && passwordMissing) {
      setErr("Password required when encryption is on.");
      return;
    }
    setSubmitting(true);
    try {
      if (!withOverrides) {
        await onRun(undefined);
      } else {
        const overrides: BackupOverridesRequest = {
          backup_area: area,
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
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={title}>
      <div className="space-y-3">
        <p className="text-xs text-muted-fg">
          These settings apply only to this run and are not saved back to
          {mode === "all" ? " any instance" : " this instance"}.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Area">
            <select
              value={area}
              onChange={(e) => setArea(e.target.value)}
              aria-label="Backup area"
              className="h-9 w-full rounded-md border border-border bg-bg px-2 text-sm"
            >
              {PFSENSE_BACKUP_AREAS.map((a) => (
                <option key={a.value} value={a.value}>{a.label}</option>
              ))}
            </select>
          </Field>
          <div className="space-y-2 self-end">
            <Toggle label="Include RRD graph data" checked={rrd} onChange={setRrd} />
            <Toggle label="Include package information" checked={packages} onChange={setPackages} />
            <Toggle label="Include SSH host keys" checked={ssh} onChange={setSsh} />
            <Toggle label="Encrypt backup" checked={encrypt} onChange={setEncrypt} />
          </div>
        </div>
        {encrypt && (
          <Field label="Encryption password (one-shot)">
            <Input
              type="password"
              value={pw}
              onChange={(e) => setPw(e.target.value)}
              autoFocus
            />
          </Field>
        )}
        {mode === "all" && (
          <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-fg">
            <strong className="text-fg">Heads-up:</strong> these settings apply to every
            enabled instance. If an instance doesn't support the selected area (e.g. a
            package not installed on that box), its backup will fail and show up in the
            sweep's failed list. A shared encryption password will apply to every
            encrypted backup produced by this run.
          </div>
        )}
        {err && <p className="text-xs text-danger">{err}</p>}
      </div>
      <div className="mt-6 flex items-center justify-between gap-2">
        <Button variant="secondary" onClick={() => run(false)} disabled={submitting}>
          Run with stored defaults
        </Button>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={() => run(true)} disabled={submitting || passwordMissing}>
            {submitting ? "Starting…" : "Run with these options"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <Label>{label}</Label>
      <div className="mt-1">{children}</div>
    </div>
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
    <label className="flex items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="accent-accent"
      />
      <span>{label}</span>
    </label>
  );
}
