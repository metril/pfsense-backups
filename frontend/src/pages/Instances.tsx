import { cloneElement, isValidElement, useId, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import cronstrue from "cronstrue";
import {
  AlertTriangle,
  HardDriveDownload,
  KeyRound,
  Package,
  Pencil,
  Plug,
  Play,
  Plus,
  Trash2,
} from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { EmptyState } from "@/components/ui/EmptyState";
import { Select, type SelectOption } from "@/components/ui/Select";
import { SkeletonRows } from "@/components/ui/Skeleton";
import { SplitButton } from "@/components/ui/SplitButton";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { useToast } from "@/components/ui/Toast";
import { CronEditor } from "@/components/cron/CronEditor";
import {
  useBackupNow,
  useCreateInstance,
  useDeleteInstance,
  useImportBackups,
  useInstances,
  usePreflight,
  useSettings,
  useTestConnection,
  useUpdateInstance,
} from "@/api/queries";
import type { Instance, InstanceCreate } from "@/api/types";

type Draft = InstanceCreate & {
  id?: number;
  /** Pairs with a password change to trigger the re-encrypt job. */
  reencrypt_existing_backups?: boolean;
};

const blank = (): Draft => ({
  name: "",
  url: "",
  username: "",
  password: "",
  subfolder: null,
  backup_prefix: "daily",
  verify_ssl: false,
  timeout_seconds: 30,
  cron_expression: null,
  // null = inherit the global default from BackupSettings.default_timezone.
  cron_timezone: null,
  enabled: true,
  retention_count: 365,
  compress: false,
  backup_area: "",
  backup_include_rrd: false,
  backup_include_packages: true,
  backup_include_ssh: true,
  backup_encrypt: false,
  backup_encrypt_password: null,
  reencrypt_existing_backups: false,
});

// Canonical pfSense subsystem IDs for the Area dropdown. "" = Everything.
// Must match pfsense_shared/schemas.py::PFSENSE_BACKUP_AREAS; keeping
// them literal here avoids dragging the list over the wire on every page
// load. Adding a subsystem is a two-line edit (here + schemas.py).
//
// Radix Select throws on <Select.Item value="">, so the UI uses the
// AREA_ALL sentinel and translates to/from the wire format at the
// Select boundary.
const AREA_ALL = "__all__";
const areaToUi = (v: string) => (v === "" ? AREA_ALL : v);
const areaFromUi = (v: string) => (v === AREA_ALL ? "" : v);
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

function scheduleSummary(cron: string | null): string {
  if (!cron) return "Disabled";
  try {
    return cronstrue.toString(cron, { use24HourTimeFormat: true });
  } catch {
    // Fall back to the raw expression rather than swallow — the user
    // should still see something recognizable if cronstrue chokes.
    return cron;
  }
}

export function InstancesPage() {
  const { data, isPending } = useInstances();
  const [editing, setEditing] = useState<Draft | null>(null);

  const create = useCreateInstance();
  const update = useUpdateInstance();
  const del = useDeleteInstance();
  const test = useTestConnection();
  const backup = useBackupNow();
  const importBackups = useImportBackups();
  const settings = useSettings();
  const globalTimezone = settings.data?.backup?.default_timezone ?? "UTC";
  const toast = useToast();
  const confirm = useConfirm();
  const navigate = useNavigate();

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Instances</h1>
        <Button onClick={() => setEditing(blank())}>
          <Plus className="h-4 w-4" /> Add instance
        </Button>
      </div>

      {isPending ? (
        <div className="mt-6">
          <SkeletonRows count={4} />
        </div>
      ) : data!.length === 0 ? (
        <div className="mt-8">
          <EmptyState
            icon={<Plus className="h-8 w-8" />}
            headline="No instances yet"
            body="Add your first pfSense instance to start scheduling backups. You'll need the URL, an admin username, and that admin's password."
            cta={
              <Button variant="primary" size="sm" onClick={() => setEditing(blank())}>
                <Plus className="h-4 w-4" /> Add instance
              </Button>
            }
          />
        </div>
      ) : (
        <table className="mt-6 w-full text-sm">
          <thead className="text-xs uppercase text-muted-fg">
            <tr>
              <th className="text-left font-normal">Name</th>
              <th className="text-left font-normal">URL</th>
              <th className="text-left font-normal">Schedule</th>
              <th className="text-left font-normal">Retention</th>
              <th className="text-left font-normal">State</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data!.map((inst) => (
              <tr key={inst.id} className="border-t border-border">
                <td className="py-3">
                  <Link to={`/instances/${inst.id}`} className="hover:text-accent">
                    {inst.name}
                  </Link>
                </td>
                <td className="py-3 font-mono text-xs">{inst.url}</td>
                <td className="py-3 text-xs">
                  <button
                    type="button"
                    onClick={() => setEditing(toDraft(inst))}
                    className="text-left hover:text-accent"
                    title={inst.cron_expression ?? "Click to set up a schedule"}
                    aria-label={`Edit schedule for ${inst.name}`}
                  >
                    {scheduleSummary(inst.cron_expression)}
                  </button>
                </td>
                <td className="py-3">{inst.retention_count}</td>
                <td className="py-3">
                  {inst.enabled ? <Badge tone="success">on</Badge> : <Badge tone="muted">off</Badge>}
                </td>
                <td className="py-3 text-right">
                  <div className="inline-flex items-center gap-1">
                    <SplitButton
                      primaryIcon={<Play className="h-3.5 w-3.5" />}
                      primaryAriaLabel={`Backup ${inst.name} now`}
                      onPrimary={() => backup.mutate({ id: inst.id })}
                      variant="secondary"
                      compact
                      menu={[
                        {
                          label: "Backup now with options…",
                          onSelect: () => {
                            // The row-level overrides dialog isn't wired here;
                            // navigate to the Instance Detail page where the
                            // SplitButton offers the dialog. Keeps the row
                            // itself dense without adding per-row dialog state.
                            navigate(`/instances/${inst.id}`);
                          },
                        },
                      ]}
                      menuAriaLabel={`More backup options for ${inst.name}`}
                    />
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => test.mutate(inst.id)}
                      aria-label={`Test connection to ${inst.name}`}
                      title="Test connection"
                    >
                      <Plug className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={async () => {
                        const sub = inst.subfolder ? `/${inst.subfolder}` : "";
                        const ok = await confirm({
                          title: `Import backups for ${inst.name}?`,
                          description:
                            `Scans /backups${sub} and adds any *.xml / *.xml.gz ` +
                            `files that aren't already tracked. Files keep their ` +
                            `original names and paths; mtime is used for the timestamp.`,
                          confirmLabel: "Import",
                        });
                        if (!ok) return;
                        try {
                          const r = await importBackups.mutateAsync(inst.id);
                          toast.success(
                            `Imported ${r.imported}, skipped ${r.skipped} from ${r.scanned_dir}`,
                            "Import complete",
                          );
                        } catch {
                          // MutationCache's onError already surfaces the error toast.
                        }
                      }}
                      aria-label={`Import backups from disk for ${inst.name}`}
                      title="Import from disk"
                    >
                      <HardDriveDownload className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => setEditing(toDraft(inst))}
                      aria-label={`Edit ${inst.name}`}
                      title="Edit"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={async () => {
                        const ok = await confirm({
                          title: `Delete ${inst.name}?`,
                          description:
                            "The instance row and every backup row linked to it " +
                            "will be removed. Files on disk are NOT deleted.",
                          confirmLabel: "Delete",
                          tone: "danger",
                        });
                        if (ok) del.mutate(inst.id);
                      }}
                      aria-label={`Delete ${inst.name}`}
                      title="Delete"
                    >
                      <Trash2 className="h-3.5 w-3.5 text-danger" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {editing && (
        // C5: key by id ("new" for fresh adds) so the dialog remounts with
        // fresh form state whenever the user switches which instance they
        // are editing. useState's initializer-only semantics otherwise keep
        // the first-opened draft's values forever.
        <EditorDialog
          key={editing.id ?? "new"}
          draft={editing}
          globalTimezone={globalTimezone}
          onClose={() => setEditing(null)}
          onSave={async (d) => {
            if (d.id === undefined) {
              await create.mutateAsync(d);
            } else {
              const { id, ...patch } = d;
              // Avoid sending an empty password — backend keeps existing ciphertext when blank.
              if (!patch.password) delete (patch as Record<string, unknown>).password;
              const response = await update.mutateAsync({ id, patch });
              if (response?.reencrypt_job_id) {
                toast.info(
                  `Job #${response.reencrypt_job_id} is rewriting previously ` +
                    `encrypted backups with the new password. Watch progress in the Jobs page.`,
                  "Re-encrypting existing backups",
                );
              }
            }
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

function toDraft(inst: Instance): Draft {
  return {
    id: inst.id,
    name: inst.name,
    url: inst.url,
    username: inst.username,
    password: "",   // blank = keep existing
    subfolder: inst.subfolder,
    backup_prefix: inst.backup_prefix,
    verify_ssl: inst.verify_ssl,
    timeout_seconds: inst.timeout_seconds,
    cron_expression: inst.cron_expression,
    cron_timezone: inst.cron_timezone,
    enabled: inst.enabled,
    retention_count: inst.retention_count,
    compress: inst.compress,
    backup_area: inst.backup_area ?? "",
    backup_include_rrd: inst.backup_include_rrd,
    backup_include_packages: inst.backup_include_packages,
    backup_include_ssh: inst.backup_include_ssh,
    backup_encrypt: inst.backup_encrypt,
    // "__set__" round-trip: if the server says one is stored, we keep
    // that sentinel so an unchanged save leaves the ciphertext alone.
    backup_encrypt_password: inst.backup_encrypt_password,
    reencrypt_existing_backups: false,
  };
}

function EditorDialog({
  draft,
  globalTimezone,
  onClose,
  onSave,
}: {
  draft: Draft;
  globalTimezone: string;
  onClose: () => void;
  onSave: (d: Draft) => Promise<void>;
}) {
  const [d, setD] = useState(draft);
  const [saving, setSaving] = useState(false);
  const preflight = usePreflight();
  const [preflightMsg, setPreflightMsg] = useState<
    { ok: boolean; detail: string; duration_ms: number } | null
  >(null);

  async function save() {
    setSaving(true);
    try {
      await onSave(d);
    } finally {
      setSaving(false);
    }
  }

  async function runPreflight() {
    setPreflightMsg(null);
    try {
      const r = await preflight.mutateAsync({
        // Edit flow: if the user didn't touch the password, we pass the
        // instance_id so the server pulls the stored ciphertext. Create flow
        // has no id and sends the raw creds.
        instance_id: d.id,
        url: d.url || undefined,
        username: d.username || undefined,
        password: d.password || undefined,
        verify_ssl: d.verify_ssl ?? false,
        timeout_seconds: d.timeout_seconds ?? 15,
      });
      setPreflightMsg(r);
    } catch (e) {
      setPreflightMsg({ ok: false, detail: String(e), duration_ms: 0 });
    }
  }

  const isNew = d.id === undefined;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={isNew ? "Add instance" : `Edit ${d.name}`}>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Name"><Input value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} /></Field>
        <Field label="URL">
          <Input
            type="url"
            value={d.url}
            onChange={(e) => setD({ ...d, url: e.target.value })}
            placeholder="https://pfsense.example.com"
          />
        </Field>
        <Field label="Username"><Input value={d.username} onChange={(e) => setD({ ...d, username: e.target.value })} /></Field>
        <Field label={isNew ? "Password" : "Password (leave blank to keep)"}>
          <Input type="password" value={d.password} onChange={(e) => setD({ ...d, password: e.target.value })} />
        </Field>
        <Field label="Subfolder"><Input value={d.subfolder ?? ""} onChange={(e) => setD({ ...d, subfolder: e.target.value || null })} /></Field>
        <Field label="Backup prefix"><Input value={d.backup_prefix} onChange={(e) => setD({ ...d, backup_prefix: e.target.value })} /></Field>
        <Field label="Timeout (s)">
          <Input
            type="number"
            min={1}
            value={d.timeout_seconds}
            onChange={(e) => {
              const v = e.target.valueAsNumber;
              if (Number.isFinite(v) && v > 0) setD({ ...d, timeout_seconds: v });
            }}
          />
        </Field>
        <Field label="Retention count">
          <Input
            type="number"
            min={1}
            value={d.retention_count}
            onChange={(e) => {
              const v = e.target.valueAsNumber;
              if (Number.isFinite(v) && v > 0) setD({ ...d, retention_count: v });
            }}
          />
        </Field>

        <Field label="Verify SSL">
          <Switch
            label="Verify SSL"
            checked={d.verify_ssl ?? false}
            onChange={(v) => setD({ ...d, verify_ssl: v })}
          />
        </Field>
        <Field label="Compress">
          <Switch
            label="Compress backups"
            checked={d.compress ?? false}
            onChange={(v) => setD({ ...d, compress: v })}
          />
        </Field>
        <Field label="Enabled">
          <Switch
            label="Instance enabled"
            checked={d.enabled ?? true}
            onChange={(v) => setD({ ...d, enabled: v })}
          />
        </Field>

        <div className="col-span-2">
          <Label>Schedule (cron)</Label>
          <CronEditor
            value={d.cron_expression ?? null}
            onChange={(v) => setD({ ...d, cron_expression: v })}
            timezone={d.cron_timezone ?? null}
            globalTimezone={globalTimezone}
            onTimezoneChange={(v) => setD({ ...d, cron_timezone: v })}
          />
        </div>

        <div className="col-span-2 border-t border-border pt-4">
          <BackupContentsSection d={d} setD={setD} isNew={isNew} />
        </div>
      </div>

      {preflightMsg && (
        <div
          className={
            "mt-4 rounded-md border px-3 py-2 text-sm " +
            (preflightMsg.ok
              ? "border-ok/50 bg-ok/10 text-ok"
              : "border-danger/50 bg-danger/10 text-danger")
          }
          role="status"
        >
          <div className="font-medium">
            {preflightMsg.ok ? "Connection OK" : "Connection failed"}{" "}
            <span className="font-normal text-muted-fg">
              ({preflightMsg.duration_ms} ms)
            </span>
          </div>
          <div className="mt-0.5 text-xs">{preflightMsg.detail}</div>
        </div>
      )}

      <div className="mt-6 flex items-center justify-between gap-2">
        <Button
          variant="secondary"
          onClick={runPreflight}
          disabled={preflight.isPending || saving || !d.url || !d.username}
          title={
            !d.url || !d.username
              ? "Fill in URL and username first"
              : "Run a live login against this pfSense"
          }
        >
          {preflight.isPending ? "Testing…" : "Test connection"}
        </Button>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={saving}>{saving ? "Saving…" : "Save"}</Button>
        </div>
      </div>
    </Dialog>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  // Associate the <label> with the wrapped control so screen readers
  // announce it. ``useId`` gives a stable SSR-safe identifier; we
  // clone the child to inject ``id`` when possible, and fall back
  // silently if the child isn't a single element (rare — most
  // Fields wrap Input / Select / native form controls).
  const id = useId();
  const controlId = `${id}-control`;
  const labelled = isValidElement(children)
    ? cloneElement(children as React.ReactElement<{ id?: string }>, {
        id: (children.props as { id?: string }).id ?? controlId,
      })
    : children;
  return (
    <div>
      <Label htmlFor={controlId}>{label}</Label>
      <div className="mt-1">{labelled}</div>
    </div>
  );
}

function BackupContentsSection({
  d,
  setD,
  isNew,
}: {
  d: Draft;
  setD: (v: Draft) => void;
  isNew: boolean;
}) {
  const hasStoredPassword = d.backup_encrypt_password === "__set__";
  // The re-encrypt checkbox is only meaningful when Encrypt is on AND
  // the user is supplying a new plaintext password (not the sentinel).
  const canReencrypt =
    !isNew &&
    d.backup_encrypt === true &&
    typeof d.backup_encrypt_password === "string" &&
    d.backup_encrypt_password !== "__set__" &&
    d.backup_encrypt_password.trim().length > 0;

  const passwordInvalid =
    d.backup_encrypt &&
    (!d.backup_encrypt_password ||
      (typeof d.backup_encrypt_password === "string" &&
        d.backup_encrypt_password.trim() === "" &&
        !hasStoredPassword));

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Package className="h-4 w-4 text-fg" aria-hidden />
        <h3 className="text-sm font-semibold">Backup contents</h3>
      </div>
      <p className="text-xs text-muted-fg">
        Maps onto pfSense's <code>Diagnostics → Backup &amp; Restore</code> form.
        Defaults mirror today's behavior so upgrades don't change what gets captured.
      </p>

      <ContentsSubsection
        icon={<Package className="h-4 w-4" aria-hidden />}
        title="Area"
      >
        <Select
          value={areaToUi(d.backup_area ?? "")}
          onChange={(v) => setD({ ...d, backup_area: areaFromUi(v) })}
          options={PFSENSE_BACKUP_AREAS}
          aria-label="Backup area"
        />
      </ContentsSubsection>

      <ContentsSubsection
        icon={<Package className="h-4 w-4" aria-hidden />}
        title="Contents"
      >
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <Checkbox
            label="Include RRD graph data"
            checked={d.backup_include_rrd ?? false}
            onChange={(v) => setD({ ...d, backup_include_rrd: v })}
          />
          <Checkbox
            label="Include package information"
            checked={d.backup_include_packages ?? true}
            onChange={(v) => setD({ ...d, backup_include_packages: v })}
          />
          <Checkbox
            label="Include SSH host keys"
            checked={d.backup_include_ssh ?? true}
            onChange={(v) => setD({ ...d, backup_include_ssh: v })}
          />
        </div>
      </ContentsSubsection>

      <ContentsSubsection
        icon={<KeyRound className="h-4 w-4" aria-hidden />}
        title="Encryption"
      >
        <Checkbox
          label="Encrypt backup"
          checked={d.backup_encrypt ?? false}
          onChange={(v) =>
            setD({
              ...d,
              backup_encrypt: v,
              // Keep whatever the user has typed / the stored sentinel
              // across toggle cycles so a fat-finger off/on doesn't
              // silently drop their new password. The server clears
              // the ciphertext when backup_encrypt=false lands anyway.
              reencrypt_existing_backups: v
                ? d.reencrypt_existing_backups
                : false,
            })
          }
        />
        {d.backup_encrypt && (
          <div className="mt-3">
            <Label>
              {hasStoredPassword
                ? "Encryption password (leave blank to keep)"
                : "Encryption password"}
            </Label>
            <Input
              type="password"
              value={
                d.backup_encrypt_password === "__set__"
                  ? ""
                  : (d.backup_encrypt_password ?? "")
              }
              placeholder={hasStoredPassword ? "•••••••• (stored)" : ""}
              onChange={(e) => {
                const v = e.target.value;
                if (v === "" && hasStoredPassword) {
                  setD({ ...d, backup_encrypt_password: "__set__" });
                } else {
                  setD({ ...d, backup_encrypt_password: v });
                }
              }}
              className="mt-1"
              aria-invalid={passwordInvalid}
              aria-describedby={passwordInvalid ? "backup-encrypt-password-err" : undefined}
            />
            {passwordInvalid && (
              <p id="backup-encrypt-password-err" className="mt-1 text-xs text-danger">
                Password required when encryption is on.
              </p>
            )}
          </div>
        )}
        {canReencrypt && (
          <div className="mt-3 flex items-start gap-2 rounded-md border border-warn/30 bg-warn/10 px-3 py-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden />
            <label className="flex cursor-pointer items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={d.reencrypt_existing_backups ?? false}
                onChange={(e) =>
                  setD({ ...d, reencrypt_existing_backups: e.target.checked })
                }
                className="mt-1 h-4 w-4 cursor-pointer accent-accent"
              />
              <span>
                Also re-encrypt existing backups with the new password.
                <span className="mt-0.5 block text-xs text-muted-fg">
                  Old-password files become unreadable once this finishes. Progress
                  shows up on the Jobs page.
                </span>
              </span>
            </label>
          </div>
        )}
      </ContentsSubsection>
    </div>
  );
}

function ContentsSubsection({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-border bg-muted/30 p-4">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-fg">
        <span className="text-fg">{icon}</span>
        {title}
      </div>
      {children}
    </section>
  );
}

function Checkbox({
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

function Switch({
  checked,
  onChange,
  label,
  id,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  /** Optional id to forward to the underlying button. The ``Field``
   *  wrapper assigns this via ``cloneElement`` so ``<Label htmlFor>``
   *  resolves to a real element — without it, clicking the visual
   *  label didn't focus/toggle the switch. */
  id?: string;
}) {
  // M6 (a11y): expose as a proper switch so screen readers announce it.
  return (
    <button
      type="button"
      id={id}
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`mt-1 inline-flex h-5 w-9 items-center rounded-full transition-colors ${
        checked ? "bg-accent" : "bg-muted"
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-fg transition-transform ${
          checked ? "translate-x-4" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}
