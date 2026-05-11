import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { AlertTriangle, KeyRound, Package } from "lucide-react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Label } from "@/components/ui/Label";
import { type SelectOption } from "@/components/ui/Select";
import {
  FormCheckbox,
  FormInput,
  FormSelect,
} from "@/components/ui/form";
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

type OverridesForm = {
  area: string;
  rrd: boolean;
  packages: boolean;
  ssh: boolean;
  encrypt: boolean;
  pw: string;
};

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
  const { control, handleSubmit, watch, getValues } = useForm<OverridesForm>({
    defaultValues: {
      area: AREA_ALL,
      rrd: false,
      packages: true,
      ssh: true,
      encrypt: false,
      pw: "",
    },
  });
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const inFlight = useRef(false);

  const encrypt = watch("encrypt");
  const pw = watch("pw");
  const passwordMissing = encrypt && pw.trim().length === 0;

  async function runStoredDefaults() {
    if (inFlight.current) return;
    setErr(null);
    inFlight.current = true;
    setSubmitting(true);
    try {
      await onRun(undefined);
      onClose();
    } catch (e) {
      setErr(String(e));
    } finally {
      setSubmitting(false);
      inFlight.current = false;
    }
  }

  const runWithOverrides = handleSubmit(async (data) => {
    if (inFlight.current) return;
    setErr(null);
    if (data.encrypt && data.pw.trim().length === 0) {
      setErr("Password required when encryption is on.");
      return;
    }
    inFlight.current = true;
    setSubmitting(true);
    try {
      const overrides: BackupOverridesRequest = {
        backup_area: data.area === AREA_ALL ? "" : data.area,
        backup_include_rrd: data.rrd,
        backup_include_packages: data.packages,
        backup_include_ssh: data.ssh,
        backup_encrypt: data.encrypt,
      };
      if (data.encrypt) overrides.backup_encrypt_password = data.pw;
      await onRun(overrides);
      onClose();
    } catch (e) {
      setErr(String(e));
    } finally {
      setSubmitting(false);
      inFlight.current = false;
    }
  });

  // Silence unused-var lint for getValues — kept for parity / future use.
  void getValues;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={title}>
      <form onSubmit={runWithOverrides} noValidate>
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
            <FormSelect
              control={control}
              name="area"
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
              <FormCheckbox control={control} name="rrd" label="Include RRD graph data" />
              <FormCheckbox control={control} name="packages" label="Include package information" />
              <FormCheckbox control={control} name="ssh" label="Include SSH host keys" />
            </div>
          </Section>

          <Section
            icon={<KeyRound className="h-4 w-4" aria-hidden />}
            title="Encryption"
            hint="Encrypt the config file with AES-256-CBC. pfSense's Restore flow accepts the output directly."
          >
            <FormCheckbox control={control} name="encrypt" label="Encrypt backup" />
            {encrypt && (
              <div className="mt-3">
                <Label>Encryption password (one-shot)</Label>
                <FormInput
                  control={control}
                  name="pw"
                  type="password"
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
          <Button
            type="button"
            variant="secondary"
            onClick={runStoredDefaults}
            disabled={submitting}
          >
            Run with stored defaults
          </Button>
          <div className="flex gap-2">
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting || passwordMissing}>
              {submitting ? "Starting…" : "Run with these options"}
            </Button>
          </div>
        </div>
      </form>
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
