import {
  cloneElement,
  isValidElement,
  useEffect,
  useId,
  useMemo,
  useState,
} from "react";
import { useBlocker } from "react-router-dom";
import { Controller, useForm, useWatch } from "react-hook-form";
import { Trash2 } from "lucide-react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { Dialog } from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { QueryError } from "@/components/ui/QueryError";
import { Select, type SelectOption } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import { useToast } from "@/components/ui/Toast";
import { FormInput, FormSelect, FormSwitch, FormTextarea } from "@/components/ui/form";
import { formatLocal } from "@/lib/datetime";
import { supportedTimezones } from "@/lib/timezones";
import {
  useApiTokens,
  useCreateApiToken,
  useDeleteApiToken,
  useSettings,
  useTestReplication,
  useUpdateApiToken,
  useUpdateBackupSettings,
  useUpdateLoggingSettings,
  useUpdateReplicationSettings,
} from "@/api/queries";
import type { ApiTokenCreated, SettingsReplication } from "@/api/types";

type BackupForm = {
  filename_format: string;
  timestamp_format: string;
  directory: string;
  default_timezone: string;
  backup_all_max_workers: number;
};

type LoggingForm = {
  level: string;
  format: string;
};

const BACKUP_DEFAULTS: BackupForm = {
  filename_format: "",
  timestamp_format: "",
  directory: "",
  default_timezone: "UTC",
  backup_all_max_workers: 4,
};

const LOGGING_DEFAULTS: LoggingForm = {
  level: "INFO",
  format: "",
};

export function SettingsPage() {
  const settings = useSettings();
  const updateBackup = useUpdateBackupSettings();
  const updateLogging = useUpdateLoggingSettings();

  const backupForm = useForm<BackupForm>({ defaultValues: BACKUP_DEFAULTS });
  const loggingForm = useForm<LoggingForm>({ defaultValues: LOGGING_DEFAULTS });

  const tzOptions: SelectOption[] = useMemo(
    () => supportedTimezones().map((tz) => ({ value: tz, label: tz })),
    [],
  );
  const tzValues = useMemo(
    () => new Set(tzOptions.map((o) => o.value)),
    [tzOptions],
  );

  // When the stored timezone isn't in the browser's IANA list (older
  // Chromium builds, exotic zones), render an inline text input instead
  // of the dropdown. The "__custom__" entry lets users opt into that
  // mode intentionally.
  const [customTz, setCustomTz] = useState(false);

  // Re-baseline both forms whenever the server data changes; ``reset``
  // also flips ``formState.isDirty`` back to false so save → refetch
  // settles the dirty indicator.
  useEffect(() => {
    if (settings.data?.backup) backupForm.reset(settings.data.backup);
    if (settings.data?.logging) loggingForm.reset(settings.data.logging);
  }, [settings.data, backupForm, loggingForm]);

  const defaultTimezone = useWatch({
    control: backupForm.control,
    name: "default_timezone",
  });

  useEffect(() => {
    if (defaultTimezone && !tzValues.has(defaultTimezone)) {
      setCustomTz(true);
    }
  }, [defaultTimezone, tzValues]);

  const isDirty =
    backupForm.formState.isDirty || loggingForm.formState.isDirty;

  // React Router v6.4+ blocker — fires on in-app navigation. Combined
  // with a ``beforeunload`` for full-page reload / close. ``confirm``
  // is deliberately synchronous so keyboard Enter on the native dialog
  // does the right thing; React Router 7's modal pattern would be a
  // bigger refactor.
  useBlocker(({ currentLocation, nextLocation }) => {
    if (!isDirty) return false;
    if (currentLocation.pathname === nextLocation.pathname) return false;
    return !window.confirm(
      "You have unsaved settings. Leave and discard changes?",
    );
  });
  useEffect(() => {
    if (!isDirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      // Most browsers ignore the custom string since 2019; the empty
      // string + preventDefault still triggers their own "leave site?"
      // dialog which is what we actually want.
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [isDirty]);

  const onSaveBackup = backupForm.handleSubmit((data) =>
    updateBackup.mutate(data),
  );
  const onSaveLogging = loggingForm.handleSubmit((data) =>
    updateLogging.mutate(data),
  );

  if (settings.isPending) return <div className="text-sm text-muted-fg">Loading…</div>;

  // Don't render editable forms seeded with empty defaults when the
  // settings fetch failed — saving them would clobber real values.
  if (settings.isError) {
    return <QueryError title="Could not load settings" error={settings.error} />;
  }

  return (
    <div className="max-w-2xl space-y-8">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <form onSubmit={onSaveBackup} noValidate>
        <section className="space-y-3">
          <h2 className="text-lg font-medium">Backup file layout</h2>
          <Field label="Filename format">
            <FormInput control={backupForm.control} name="filename_format" />
          </Field>
          <Field label="Timestamp format (strftime)">
            <FormInput control={backupForm.control} name="timestamp_format" />
          </Field>
          <Field label="Directory">
            <FormInput control={backupForm.control} name="directory" />
          </Field>
          <Field label="Default scheduler timezone">
            {customTz ? (
              <div className="space-y-1">
                <FormInput
                  control={backupForm.control}
                  name="default_timezone"
                  placeholder="e.g. America/Los_Angeles"
                />
                <button
                  type="button"
                  className="text-xs text-accent hover:underline"
                  onClick={() => {
                    setCustomTz(false);
                    backupForm.setValue("default_timezone", "UTC", {
                      shouldDirty: true,
                    });
                  }}
                >
                  ← pick from the list instead
                </button>
              </div>
            ) : (
              <FormSelect
                control={backupForm.control}
                name="default_timezone"
                options={tzOptions}
                aria-label="Default scheduler timezone"
                customOption={{ label: "Custom…" }}
              />
            )}
            <p className="mt-1 text-xs text-muted-fg">
              Used for every instance's schedule unless that instance sets its own override.
              Changing this tells the worker to reload every cron trigger.
            </p>
          </Field>
          <Field label='Parallel backups ("Backup all")'>
            <FormInput
              control={backupForm.control}
              name="backup_all_max_workers"
              type="number"
              min={1}
              max={32}
              numericFallback={4}
            />
            <p className="mt-1 text-xs text-muted-fg">
              Cap on instances processed concurrently during a full sweep. 1 = serial;
              higher values speed up large fleets at the cost of more simultaneous
              pfSense logins. Default 4.
            </p>
          </Field>
          <div className="flex justify-end">
            <Button type="submit" disabled={updateBackup.isPending}>
              {updateBackup.isPending ? "Saving…" : "Save backup settings"}
            </Button>
          </div>
        </section>
      </form>

      <form onSubmit={onSaveLogging} noValidate>
        <section className="space-y-3">
          <h2 className="text-lg font-medium">Logging</h2>
          <Field label="Level">
            <FormSelect
              control={loggingForm.control}
              name="level"
              options={["DEBUG", "INFO", "WARNING", "ERROR"].map((l) => ({
                value: l,
                label: l,
              }))}
              aria-label="Log level"
            />
          </Field>
          <Field label="Format">
            <FormInput control={loggingForm.control} name="format" />
          </Field>
          <div className="flex justify-end">
            <Button type="submit" disabled={updateLogging.isPending}>
              {updateLogging.isPending ? "Saving…" : "Save logging settings"}
            </Button>
          </div>
        </section>
      </form>

      <ReplicationSection initial={settings.data?.replication ?? null} />

      <ApiTokensSection />
    </div>
  );
}

const REPLICATION_DEFAULTS: SettingsReplication = {
  enabled: false,
  kind: "s3",
  s3_endpoint_url: null,
  s3_region: null,
  s3_bucket: null,
  s3_access_key_id: null,
  s3_secret_access_key: null,
  sftp_host: null,
  sftp_port: 22,
  sftp_username: null,
  sftp_password: null,
  sftp_private_key: null,
  base_path: "pfsense-backups",
  encrypt_plaintext: true,
  double_encrypt: false,
  replication_password: null,
  mirror_deletes: false,
};

function ReplicationSection({ initial }: { initial: SettingsReplication | null }) {
  const update = useUpdateReplicationSettings();
  const test = useTestReplication();
  const toast = useToast();
  const form = useForm<SettingsReplication>({
    defaultValues: initial ?? REPLICATION_DEFAULTS,
  });
  useEffect(() => {
    if (initial) form.reset(initial);
  }, [initial, form]);

  const kind = useWatch({ control: form.control, name: "kind" });
  const enabled = useWatch({ control: form.control, name: "enabled" });
  const encryptPlaintext = useWatch({
    control: form.control,
    name: "encrypt_plaintext",
  });
  const doubleEncrypt = useWatch({ control: form.control, name: "double_encrypt" });

  const onSave = form.handleSubmit((data) => update.mutate(data));

  async function onTest() {
    try {
      const r = await test.mutateAsync();
      if (r.ok) toast.success(`Replication target reachable: ${r.detail ?? "OK"}`);
      else toast.error(`Replication test failed: ${r.detail ?? "unknown error"}`);
    } catch {
      // Global mutation handler already toasts the error.
    }
  }

  return (
    <form onSubmit={onSave} noValidate>
      <section className="space-y-3">
        <h2 className="text-lg font-medium">Off-site replication</h2>
        <p className="text-xs text-muted-fg">
          Mirror backups of opted-in instances (per-instance toggle on the
          instance form) to one S3 or SFTP destination. Plaintext backups are
          encrypted with the replication password before upload.
        </p>

        <Field label="Enabled">
          <FormSwitch control={form.control} name="enabled" label="Replication enabled" />
        </Field>
        <Field label="Destination type">
          <Controller
            control={form.control}
            name="kind"
            render={({ field }) => (
              <Select
                value={field.value}
                onChange={field.onChange}
                options={[
                  { value: "s3", label: "S3 (AWS / MinIO / R2)" },
                  { value: "sftp", label: "SFTP" },
                ]}
                aria-label="Replication destination type"
                className="w-56"
              />
            )}
          />
        </Field>

        {kind === "s3" ? (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Bucket">
              <FormInput control={form.control} name="s3_bucket" />
            </Field>
            <Field label="Region (optional)">
              <FormInput control={form.control} name="s3_region" />
            </Field>
            <Field label="Endpoint URL (MinIO/R2; blank for AWS)">
              <FormInput control={form.control} name="s3_endpoint_url" />
            </Field>
            <Field label="Access key id">
              <FormInput control={form.control} name="s3_access_key_id" />
            </Field>
            <Field label="Secret access key">
              <FormInput control={form.control} name="s3_secret_access_key" type="password" />
            </Field>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Host">
              <FormInput control={form.control} name="sftp_host" />
            </Field>
            <Field label="Port">
              <FormInput control={form.control} name="sftp_port" type="number" min={1} numericFallback={22} />
            </Field>
            <Field label="Username">
              <FormInput control={form.control} name="sftp_username" />
            </Field>
            <Field label="Password (or use a key)">
              <FormInput control={form.control} name="sftp_password" type="password" />
            </Field>
            <div className="col-span-2">
              <Field label="Private key (PEM, optional — takes precedence)">
                <FormTextarea control={form.control} name="sftp_private_key" rows={3} />
              </Field>
            </div>
          </div>
        )}

        <Field label="Remote base path">
          <FormInput control={form.control} name="base_path" />
        </Field>

        <Field label="Encrypt plaintext backups">
          <FormSwitch
            control={form.control}
            name="encrypt_plaintext"
            label="Encrypt plaintext backups before upload"
          />
        </Field>
        {!encryptPlaintext && (
          <Alert tone="warn" title="Plaintext off-site">
            Unencrypted backups will land off-site as plain config.xml —
            including password hashes, VPN PSKs, and certificate keys.
          </Alert>
        )}
        <Field label="Double-encrypt">
          <FormSwitch
            control={form.control}
            name="double_encrypt"
            label="Also wrap already-encrypted backups"
          />
        </Field>
        {doubleEncrypt && (
          <Alert tone="info" title="Double-wrapped objects need two steps to restore">
            Off-site objects with the <code>.2x</code> suffix must have the
            outer layer stripped first (<code>python -m worker decrypt-replica</code>)
            before diag_backup.php will accept them.
          </Alert>
        )}
        <Field label="Replication password">
          <FormInput control={form.control} name="replication_password" type="password" />
        </Field>
        <p className="text-xs text-muted-fg">
          Off-site objects restore through pfSense's own restore page with
          just this password — store it somewhere that survives this host.
        </p>
        <Field label="Mirror deletes">
          <FormSwitch
            control={form.control}
            name="mirror_deletes"
            label="Delete remote copies when retention prunes local ones"
          />
        </Field>
        {!form.getValues("mirror_deletes") && enabled && (
          <p className="text-xs text-muted-fg">
            Keep-forever mode: pruned backups stay listed as "off-site only"
            and can be retrieved; use S3 lifecycle rules for remote pruning.
          </p>
        )}

        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="secondary"
            onClick={onTest}
            disabled={test.isPending || !enabled}
          >
            {test.isPending ? "Testing…" : "Test connection"}
          </Button>
          <Button type="submit" disabled={update.isPending}>
            {update.isPending ? "Saving…" : "Save replication settings"}
          </Button>
        </div>
      </section>
    </form>
  );
}

function ApiTokensSection() {
  const tokens = useApiTokens();
  const create = useCreateApiToken();
  const update = useUpdateApiToken();
  const del = useDeleteApiToken();
  const confirm = useConfirm();
  const [name, setName] = useState("");
  const [scope, setScope] = useState<"read" | "write">("read");
  const [minted, setMinted] = useState<ApiTokenCreated | null>(null);
  const [copied, setCopied] = useState(false);

  async function onCreate() {
    if (!name.trim()) return;
    const created = await create.mutateAsync({ name: name.trim(), scope });
    setMinted(created);
    setCopied(false);
    setName("");
  }

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-medium">API tokens</h2>
      <p className="text-xs text-muted-fg">
        Bearer tokens for automation (<code>Authorization: Bearer pfsb_…</code>).
        Read scope allows GET only; write scope allows everything except
        managing tokens. The secret is shown once at creation.
      </p>

      {tokens.isError && (
        <QueryError title="Could not load API tokens" error={tokens.error} />
      )}
      {(tokens.data ?? []).length > 0 && (
        <table className="w-full text-sm">
          <thead className="text-xs uppercase text-muted-fg">
            <tr>
              <th className="text-left font-normal">Name</th>
              <th className="text-left font-normal">Prefix</th>
              <th className="text-left font-normal">Scope</th>
              <th className="text-left font-normal">Last used</th>
              <th className="text-left font-normal">Expires</th>
              <th className="text-left font-normal">Enabled</th>
              <th className="w-12"></th>
            </tr>
          </thead>
          <tbody>
            {(tokens.data ?? []).map((t) => (
              <tr key={t.id} className="border-t border-border">
                <td className="py-2">{t.name}</td>
                <td className="py-2 font-mono text-xs">{t.prefix}…</td>
                <td className="py-2 text-xs">{t.scope}</td>
                <td className="py-2 text-xs text-muted-fg">
                  {t.last_used_at ? formatLocal(t.last_used_at) : "never"}
                </td>
                <td className="py-2 text-xs text-muted-fg">
                  {t.expires_at ? formatLocal(t.expires_at) : "—"}
                </td>
                <td className="py-2">
                  <Switch
                    checked={t.enabled}
                    onChange={(v) => update.mutate({ id: t.id, enabled: v })}
                    label={`${t.enabled ? "Disable" : "Enable"} ${t.name}`}
                  />
                </td>
                <td className="py-2 text-right">
                  <Button
                    variant="ghost"
                    size="icon"
                    title="Delete"
                    aria-label={`Delete token ${t.name}`}
                    onClick={async () => {
                      const ok = await confirm({
                        title: `Delete token ${t.name}?`,
                        description:
                          "Clients using it will start receiving 401s immediately.",
                        confirmLabel: "Delete",
                        tone: "danger",
                      });
                      if (ok) del.mutate(t.id);
                    }}
                  >
                    <Trash2 className="h-4 w-4 text-danger" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="flex items-end gap-2">
        <Field label="New token name">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="ci-export"
          />
        </Field>
        <Field label="Scope">
          <Select
            value={scope}
            onChange={(v) => setScope(v as "read" | "write")}
            options={[
              { value: "read", label: "read-only" },
              { value: "write", label: "read + write" },
            ]}
            aria-label="Token scope"
            className="w-40"
          />
        </Field>
        <Button onClick={onCreate} disabled={!name.trim() || create.isPending}>
          {create.isPending ? "Creating…" : "Create token"}
        </Button>
      </div>

      {minted && (
        <Dialog
          open
          onOpenChange={(open) => {
            if (!open) setMinted(null);
          }}
          title={`Token ${minted.name} created`}
        >
          <p className="text-sm">
            Copy the secret now — it is <strong>not retrievable later</strong>.
          </p>
          <div className="mt-2 flex items-center gap-2">
            <code className="flex-1 overflow-x-auto rounded bg-muted/40 p-2 font-mono text-xs">
              {minted.token}
            </code>
            <Button
              size="sm"
              variant="secondary"
              onClick={async () => {
                await navigator.clipboard.writeText(minted.token);
                setCopied(true);
              }}
            >
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
          <div className="mt-4 flex justify-end">
            <Button onClick={() => setMinted(null)}>Done</Button>
          </div>
        </Dialog>
      )}
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  // See Instances.tsx::Field — same htmlFor+id plumbing so screen
  // readers announce each form control with its visible label.
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
