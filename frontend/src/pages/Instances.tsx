import { cloneElement, isValidElement, useId, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Controller,
  useForm,
  useWatch,
  type Control,
  type UseFormSetValue,
} from "react-hook-form";
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
import { Checkbox } from "@/components/ui/Checkbox";
import { EmptyState } from "@/components/ui/EmptyState";
import { Select, type SelectOption } from "@/components/ui/Select";
import { SkeletonRows } from "@/components/ui/Skeleton";
import { SplitButton } from "@/components/ui/SplitButton";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { useToast } from "@/components/ui/Toast";
import {
  FormCheckbox,
  FormCronEditor,
  FormInput,
  FormSwitch,
} from "@/components/ui/form";
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
  const { control, handleSubmit, getValues, setValue, watch, formState } = useForm<Draft>({
    defaultValues: draft,
  });
  const [saving, setSaving] = useState(false);
  const preflight = usePreflight();
  const [preflightMsg, setPreflightMsg] = useState<
    { ok: boolean; detail: string; duration_ms: number } | null
  >(null);

  const isNew = draft.id === undefined;
  // Header title + filename-prefix preview both need the live ``name``.
  // ``watch('name')`` re-renders only this component when ``name`` changes,
  // not the entire form tree — so we can use it liberally.
  const nameLive = watch("name");
  const urlLive = watch("url");
  const usernameLive = watch("username");

  const onSubmit = handleSubmit(async (data) => {
    setSaving(true);
    try {
      await onSave(data);
    } finally {
      setSaving(false);
    }
  });

  async function runPreflight() {
    setPreflightMsg(null);
    const v = getValues();
    try {
      const r = await preflight.mutateAsync({
        // Edit flow: if the user didn't touch the password, we pass the
        // instance_id so the server pulls the stored ciphertext. Create flow
        // has no id and sends the raw creds.
        instance_id: v.id,
        url: v.url || undefined,
        username: v.username || undefined,
        password: v.password || undefined,
        verify_ssl: v.verify_ssl ?? false,
        timeout_seconds: v.timeout_seconds ?? 15,
      });
      setPreflightMsg(r);
    } catch (e) {
      setPreflightMsg({ ok: false, detail: String(e), duration_ms: 0 });
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={isNew ? "Add instance" : `Edit ${nameLive}`}
    >
      <form onSubmit={onSubmit} noValidate>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Name"><FormInput control={control} name="name" /></Field>
          <Field label="URL">
            <FormInput
              control={control}
              name="url"
              type="url"
              placeholder="https://pfsense.example.com"
            />
          </Field>
          <Field label="Username"><FormInput control={control} name="username" /></Field>
          <Field label={isNew ? "Password" : "Password (leave blank to keep)"}>
            <FormInput control={control} name="password" type="password" />
          </Field>
          <Field label="Subfolder">
            <FormInput control={control} name="subfolder" />
          </Field>
          <Field label="Backup prefix">
            <FormInput control={control} name="backup_prefix" placeholder="daily" />
            <p className="mt-1 text-xs text-muted-fg">
              Prefix for backup filenames — e.g. <code>daily</code> produces{" "}
              <code>daily-{nameLive || "instance"}-2026-04-20.xml</code>.
            </p>
          </Field>
          <Field label="Timeout (s)">
            <FormInput control={control} name="timeout_seconds" type="number" min={1} numericFallback={30} />
          </Field>
          <Field label="Retention count">
            <FormInput control={control} name="retention_count" type="number" min={1} numericFallback={365} />
          </Field>

          <Field label="Verify SSL">
            <FormSwitch control={control} name="verify_ssl" label="Verify SSL" />
          </Field>
          <Field label="Compress">
            <FormSwitch control={control} name="compress" label="Compress backups" />
          </Field>
          <Field label="Enabled">
            <FormSwitch control={control} name="enabled" label="Instance enabled" />
          </Field>

          <div className="col-span-2">
            <Label>Schedule (cron)</Label>
            <FormCronEditor
              control={control}
              valueName="cron_expression"
              timezoneName="cron_timezone"
              globalTimezone={globalTimezone}
            />
          </div>

          <div className="col-span-2 border-t border-border pt-4">
            <BackupContentsSection control={control} setValue={setValue} isNew={isNew} />
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
            type="button"
            variant="secondary"
            onClick={runPreflight}
            disabled={preflight.isPending || saving || !urlLive || !usernameLive}
            title={
              !urlLive || !usernameLive
                ? "Fill in URL and username first"
                : "Run a live login against this pfSense"
            }
          >
            {preflight.isPending ? "Testing…" : "Test connection"}
          </Button>
          <div className="flex gap-2">
            <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={saving || formState.isSubmitting}>
              {saving ? "Saving…" : "Save"}
            </Button>
          </div>
        </div>
      </form>
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
  control,
  setValue,
  isNew,
}: {
  control: Control<Draft>;
  setValue: UseFormSetValue<Draft>;
  isNew: boolean;
}) {
  // Field-level subscriptions: this component re-renders only when the
  // four watched fields change, not when name/url/timeout/etc do.
  const backupEncrypt = useWatch({ control, name: "backup_encrypt" });
  const backupEncryptPassword = useWatch({
    control,
    name: "backup_encrypt_password",
  });

  const hasStoredPassword = backupEncryptPassword === "__set__";
  const canReencrypt =
    !isNew &&
    backupEncrypt === true &&
    typeof backupEncryptPassword === "string" &&
    backupEncryptPassword !== "__set__" &&
    backupEncryptPassword.trim().length > 0;

  const passwordInvalid =
    !!backupEncrypt &&
    (!backupEncryptPassword ||
      (typeof backupEncryptPassword === "string" &&
        backupEncryptPassword.trim() === "" &&
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
        <Controller
          control={control}
          name="backup_area"
          render={({ field }) => (
            <Select
              value={areaToUi(field.value ?? "")}
              onChange={(v) => field.onChange(areaFromUi(v))}
              options={PFSENSE_BACKUP_AREAS}
              aria-label="Backup area"
            />
          )}
        />
      </ContentsSubsection>

      <ContentsSubsection
        icon={<Package className="h-4 w-4" aria-hidden />}
        title="Contents"
      >
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <FormCheckbox
            control={control}
            name="backup_include_rrd"
            label="Include RRD graph data"
          />
          <FormCheckbox
            control={control}
            name="backup_include_packages"
            label="Include package information"
          />
          <FormCheckbox
            control={control}
            name="backup_include_ssh"
            label="Include SSH host keys"
          />
        </div>
      </ContentsSubsection>

      <ContentsSubsection
        icon={<KeyRound className="h-4 w-4" aria-hidden />}
        title="Encryption"
      >
        {/* Custom Controller for backup_encrypt: turning it off must also
            reset reencrypt_existing_backups so a fat-finger cycle doesn't
            silently re-encrypt with whatever was previously typed. */}
        <Controller
          control={control}
          name="backup_encrypt"
          render={({ field }) => (
            <Checkbox
              label="Encrypt backup"
              checked={Boolean(field.value)}
              onChange={(v) => {
                field.onChange(v);
                if (!v) {
                  setValue("reencrypt_existing_backups", false);
                }
              }}
            />
          )}
        />
        {backupEncrypt && (
          <div className="mt-3">
            <Label>
              {hasStoredPassword
                ? "Encryption password (leave blank to keep)"
                : "Encryption password"}
            </Label>
            <Controller
              control={control}
              name="backup_encrypt_password"
              render={({ field }) => (
                <Input
                  type="password"
                  value={
                    field.value === "__set__"
                      ? ""
                      : (field.value as string | null | undefined) ?? ""
                  }
                  placeholder={hasStoredPassword ? "•••••••• (stored)" : ""}
                  onChange={(e) => {
                    const v = e.target.value;
                    field.onChange(v === "" && hasStoredPassword ? "__set__" : v);
                  }}
                  className="mt-1"
                  aria-invalid={passwordInvalid}
                  aria-describedby={
                    passwordInvalid ? "backup-encrypt-password-err" : undefined
                  }
                />
              )}
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
            <FormCheckbox
              control={control}
              name="reencrypt_existing_backups"
              label="Also re-encrypt existing backups with the new password."
              className="items-start"
            />
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

// Switch and Checkbox primitives have moved to
// frontend/src/components/ui/{Switch,Checkbox}.tsx.
