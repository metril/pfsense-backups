import { useState } from "react";
import { HardDriveDownload, Pencil, Plug, Play, Plus, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { useToast } from "@/components/ui/Toast";
import { CronEditor } from "@/components/cron/CronEditor";
import {
  useBackupNow,
  useCreateInstance,
  useDeleteInstance,
  useImportBackups,
  useInstances,
  useTestConnection,
  useUpdateInstance,
} from "@/api/queries";
import type { Instance, InstanceCreate } from "@/api/types";

type Draft = InstanceCreate & { id?: number };

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
  cron_timezone: "UTC",
  enabled: true,
  retention_count: 365,
  compress: false,
});

export function InstancesPage() {
  const { data, isPending } = useInstances();
  const [editing, setEditing] = useState<Draft | null>(null);

  const create = useCreateInstance();
  const update = useUpdateInstance();
  const del = useDeleteInstance();
  const test = useTestConnection();
  const backup = useBackupNow();
  const importBackups = useImportBackups();
  const toast = useToast();

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Instances</h1>
        <Button onClick={() => setEditing(blank())}>
          <Plus className="h-4 w-4" /> Add instance
        </Button>
      </div>

      {isPending ? (
        <div className="mt-6 text-sm text-muted-fg">Loading…</div>
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
                <td className="py-3">{inst.name}</td>
                <td className="py-3 font-mono text-xs">{inst.url}</td>
                <td className="py-3 font-mono text-xs">
                  {inst.cron_expression ?? <span className="text-muted-fg">—</span>}
                </td>
                <td className="py-3">{inst.retention_count}</td>
                <td className="py-3">
                  {inst.enabled ? <Badge tone="success">on</Badge> : <Badge tone="muted">off</Badge>}
                </td>
                <td className="py-3 text-right">
                  <div className="inline-flex gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => backup.mutate(inst.id)}
                      aria-label={`Backup ${inst.name} now`}
                      title="Backup now"
                    >
                      <Play className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => test.mutate(inst.id)}
                      aria-label={`Test connection to ${inst.name}`}
                      title="Test connection"
                    >
                      <Plug className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={async () => {
                        const sub = inst.subfolder ? `/${inst.subfolder}` : "";
                        if (
                          !confirm(
                            `Import existing backup files from /backups${sub} into "${inst.name}"?\n\n` +
                              "Only files not already tracked will be added. Files keep their original " +
                              "names and paths; mtime is used for the timestamp.",
                          )
                        )
                          return;
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
                      <HardDriveDownload className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setEditing(toDraft(inst))}
                      aria-label={`Edit ${inst.name}`}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => {
                        if (confirm(`Delete ${inst.name}?`)) del.mutate(inst.id);
                      }}
                      aria-label={`Delete ${inst.name}`}
                    >
                      <Trash2 className="h-4 w-4 text-danger" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
            {data!.length === 0 && (
              <tr>
                <td colSpan={6} className="py-8 text-center text-sm text-muted-fg">
                  No instances yet.
                </td>
              </tr>
            )}
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
          onClose={() => setEditing(null)}
          onSave={async (d) => {
            if (d.id === undefined) {
              await create.mutateAsync(d);
            } else {
              const { id, ...patch } = d;
              // Avoid sending an empty password — backend keeps existing ciphertext when blank.
              if (!patch.password) delete (patch as Record<string, unknown>).password;
              await update.mutateAsync({ id, patch });
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
  };
}

function EditorDialog({ draft, onClose, onSave }: { draft: Draft; onClose: () => void; onSave: (d: Draft) => Promise<void> }) {
  const [d, setD] = useState(draft);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await onSave(d);
    } finally {
      setSaving(false);
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
        <Field label="Timeout (s)"><Input type="number" value={d.timeout_seconds} onChange={(e) => setD({ ...d, timeout_seconds: Number(e.target.value) })} /></Field>
        <Field label="Retention count"><Input type="number" value={d.retention_count} onChange={(e) => setD({ ...d, retention_count: Number(e.target.value) })} /></Field>

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
            timezone={d.cron_timezone ?? "UTC"}
            onTimezoneChange={(v) => setD({ ...d, cron_timezone: v })}
          />
        </div>
      </div>

      <div className="mt-6 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button onClick={save} disabled={saving}>{saving ? "Saving…" : "Save"}</Button>
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

function Switch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  // M6 (a11y): expose as a proper switch so screen readers announce it.
  return (
    <button
      type="button"
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
