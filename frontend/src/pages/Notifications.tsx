import { useMemo, useState } from "react";
import {
  Bell,
  ChevronDown,
  Eye,
  EyeOff,
  HeartPulse,
  Home,
  MessageCircle,
  Pencil,
  Plus,
  Send,
  Smartphone,
  Trash2,
  Webhook,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import {
  useCreateNotification,
  useDeleteNotification,
  useInstances,
  useNotifications,
  useSendTestNotification,
  useUpdateNotification,
} from "@/api/queries";
import type { Instance, Notification, NotificationKind } from "@/api/types";
import { cn } from "@/lib/cn";

// A rich in-memory draft. Secret values coming back from the server
// as "__set__" are left untouched so the PATCH round-trips them
// back and the server preserves the stored value.
type Draft = Omit<Notification, "id"> & { id?: number };

const KIND_META: Record<
  NotificationKind,
  { label: string; Icon: typeof Bell; tag: string; description: string }
> = {
  discord: {
    label: "Discord",
    Icon: MessageCircle,
    tag: "Discord",
    description: "Post to a Discord channel via webhook URL.",
  },
  home_assistant: {
    label: "Home Assistant",
    Icon: Home,
    tag: "Home Assistant",
    description: "Call a notify service or fire a webhook automation.",
  },
  ntfy: {
    label: "Ntfy",
    Icon: Smartphone,
    tag: "Ntfy",
    description: "Push to your phone via ntfy.sh or a self-hosted ntfy server.",
  },
  healthchecks: {
    label: "Healthchecks",
    Icon: HeartPulse,
    tag: "Healthchecks",
    description: "Heartbeat monitoring so you know when backups stop running.",
  },
  webhook: {
    label: "Custom webhook",
    Icon: Webhook,
    tag: "Webhook",
    description: "POST arbitrary JSON to any HTTPS endpoint.",
  },
};

function blankDraft(kind: NotificationKind): Draft {
  const baseConfig = (() => {
    switch (kind) {
      case "home_assistant":
        return { base_url: "", access_token: "", mode: "notify", service: "", title: "" };
      case "ntfy":
        return { server_url: "https://ntfy.sh", topic: "", priority: 3, tags: [] };
      case "healthchecks":
        // Manual mode by default; the auto-provision toggle flips it.
        return null;
      default:
        return null;
    }
  })();
  return {
    name: "",
    kind,
    url: "",
    trigger: kind === "healthchecks" ? "always" : "always",
    enabled: true,
    message_format: "{status}: pfSense backup completed. {details}",
    include_instance_details: true,
    timeout_seconds: 10,
    headers: null,
    payload_template: null,
    config: baseConfig,
    instance_ids: null,
  };
}

function stripId(d: Draft): Omit<Notification, "id"> {
  const { id: _id, ...rest } = d;
  void _id;
  return rest;
}

export function NotificationsPage() {
  const { data, isPending } = useNotifications();
  const instances = useInstances();
  const create = useCreateNotification();
  const update = useUpdateNotification();
  const del = useDeleteNotification();
  const send = useSendTestNotification();
  const confirm = useConfirm();
  const [picking, setPicking] = useState(false);
  const [editing, setEditing] = useState<Draft | null>(null);

  const instanceMap = useMemo(() => {
    const m = new Map<number, Instance>();
    for (const i of instances.data ?? []) m.set(i.id, i);
    return m;
  }, [instances.data]);

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Notifications</h1>
        <Button onClick={() => setPicking(true)}>
          <Plus className="h-4 w-4" /> Add notification
        </Button>
      </div>

      {isPending ? (
        <div className="mt-6 text-sm text-muted-fg">Loading…</div>
      ) : (
        <div className="mt-6 space-y-3">
          {data!.map((n) => {
            const meta = KIND_META[n.kind] ?? KIND_META.webhook;
            const scopeNames =
              n.instance_ids && n.instance_ids.length > 0
                ? n.instance_ids
                    .map((id) => instanceMap.get(id)?.name ?? `id=${id}`)
                    .join(", ")
                : null;
            return (
              <div
                key={n.id}
                className="flex items-center gap-4 rounded-lg border border-border bg-muted/20 p-4"
              >
                <meta.Icon className="h-5 w-5 text-muted-fg" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{n.name}</span>
                    <Badge tone="muted">{meta.tag}</Badge>
                    {scopeNames ? (
                      <Badge
                        tone="default"
                        className="cursor-help"
                        {...({ title: scopeNames } as Record<string, string>)}
                      >
                        {n.instance_ids!.length} instance
                        {n.instance_ids!.length === 1 ? "" : "s"}
                      </Badge>
                    ) : (
                      <Badge tone="muted">all instances</Badge>
                    )}
                  </div>
                  <div className="truncate font-mono text-xs text-muted-fg">{n.url}</div>
                </div>
                <Badge tone={n.enabled ? "success" : "muted"}>{n.trigger}</Badge>
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => send.mutate(n.id)}
                    title="Send test"
                  >
                    <Send className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setEditing({ ...n })}
                    title="Edit"
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    title="Delete"
                    onClick={async () => {
                      const ok = await confirm({
                        title: `Delete ${n.name}?`,
                        confirmLabel: "Delete",
                        tone: "danger",
                      });
                      if (ok) del.mutate(n.id);
                    }}
                  >
                    <Trash2 className="h-4 w-4 text-danger" />
                  </Button>
                </div>
              </div>
            );
          })}
          {data!.length === 0 && (
            <div className="rounded-lg border border-border bg-muted/20 p-8 text-center text-sm text-muted-fg">
              No notifications configured.
            </div>
          )}
        </div>
      )}

      {picking && (
        <KindPickerDialog
          onClose={() => setPicking(false)}
          onPick={(kind) => {
            setPicking(false);
            setEditing(blankDraft(kind));
          }}
        />
      )}

      {editing && (
        <EditorDialog
          draft={editing}
          instances={instances.data ?? []}
          onClose={() => setEditing(null)}
          onSave={async (d) => {
            if (d.id === undefined) {
              await create.mutateAsync(stripId(d));
            } else {
              const { id, ...patch } = d;
              await update.mutateAsync({ id, patch });
            }
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

// ------------------------------------------------------------------ //
// Kind picker
// ------------------------------------------------------------------ //

function KindPickerDialog({
  onPick,
  onClose,
}: {
  onPick: (kind: NotificationKind) => void;
  onClose: () => void;
}) {
  const ordered: NotificationKind[] = [
    "discord",
    "home_assistant",
    "ntfy",
    "healthchecks",
    "webhook",
  ];
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title="Add notification">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {ordered.map((k) => {
          const m = KIND_META[k];
          return (
            <button
              key={k}
              type="button"
              onClick={() => onPick(k)}
              className={cn(
                "flex items-start gap-3 rounded-lg border border-border bg-muted/20 p-4 text-left",
                "transition-colors hover:border-accent hover:bg-accent/10",
              )}
            >
              <m.Icon className="mt-0.5 h-5 w-5 text-accent" />
              <div>
                <div className="font-medium">{m.label}</div>
                <div className="mt-1 text-xs text-muted-fg">{m.description}</div>
              </div>
            </button>
          );
        })}
      </div>
    </Dialog>
  );
}

// ------------------------------------------------------------------ //
// Editor (per-kind form + common footer)
// ------------------------------------------------------------------ //

function EditorDialog({
  draft,
  instances,
  onClose,
  onSave,
}: {
  draft: Draft;
  instances: Instance[];
  onClose: () => void;
  onSave: (d: Draft) => Promise<void>;
}) {
  const [d, setD] = useState(draft);
  const [headersStr, setHeadersStr] = useState(
    d.headers ? JSON.stringify(d.headers, null, 2) : "",
  );
  const [payloadStr, setPayloadStr] = useState(
    d.payload_template ? JSON.stringify(d.payload_template, null, 2) : "",
  );
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const meta = KIND_META[d.kind] ?? KIND_META.webhook;

  async function save() {
    setError(null);
    try {
      const final: Draft = {
        ...d,
        headers: headersStr.trim() ? JSON.parse(headersStr) : null,
        payload_template: payloadStr.trim() ? JSON.parse(payloadStr) : null,
      };
      setSaving(true);
      await onSave(final);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={d.id === undefined ? `Add ${meta.label}` : `Edit ${d.name}`}
    >
      <div className="space-y-4">
        <Field label="Name">
          <Input value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} />
        </Field>

        {d.kind === "discord" && <DiscordFields d={d} setD={setD} />}
        {d.kind === "home_assistant" && <HaFields d={d} setD={setD} />}
        {d.kind === "ntfy" && <NtfyFields d={d} setD={setD} />}
        {d.kind === "healthchecks" && <HcFields d={d} setD={setD} />}
        {d.kind === "webhook" && <WebhookFields d={d} setD={setD} />}

        <Field label="Message format">
          <Input
            value={d.message_format}
            onChange={(e) => setD({ ...d, message_format: e.target.value })}
          />
          <p className="mt-1 text-xs text-muted-fg">
            Available placeholders: <code>{"{status}"}</code> and{" "}
            <code>{"{details}"}</code>.
          </p>
        </Field>

        {/* Trigger (hidden for Healthchecks — locked to "always") */}
        {d.kind !== "healthchecks" && (
          <Field label="Trigger">
            <select
              value={d.trigger}
              onChange={(e) =>
                setD({ ...d, trigger: e.target.value as Draft["trigger"] })
              }
              className="h-9 w-full rounded-md border border-border bg-bg px-2 text-sm"
            >
              <option value="always">always</option>
              <option value="success">success</option>
              <option value="failure">failure</option>
            </select>
          </Field>
        )}

        <InstanceScopeField
          value={d.instance_ids}
          instances={instances}
          onChange={(v) => setD({ ...d, instance_ids: v })}
        />

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={d.enabled}
            onChange={(e) => setD({ ...d, enabled: e.target.checked })}
          />
          enabled
        </label>

        {/* Advanced disclosure */}
        <div className="rounded-md border border-border">
          <button
            type="button"
            onClick={() => setAdvancedOpen((o) => !o)}
            className="flex w-full items-center justify-between px-3 py-2 text-sm text-muted-fg hover:text-fg"
          >
            <span>Advanced</span>
            <ChevronDown
              className={cn(
                "h-4 w-4 transition-transform",
                advancedOpen && "rotate-180",
              )}
            />
          </button>
          {advancedOpen && (
            <div className="space-y-3 border-t border-border p-3">
              <Field label="Timeout (seconds)">
                <Input
                  type="number"
                  value={d.timeout_seconds}
                  onChange={(e) =>
                    setD({ ...d, timeout_seconds: Number(e.target.value) })
                  }
                />
              </Field>
              {d.kind !== "healthchecks" && (
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={d.include_instance_details}
                    onChange={(e) =>
                      setD({ ...d, include_instance_details: e.target.checked })
                    }
                  />
                  include failed-instance names in message
                </label>
              )}
              {/* Headers/payload overrides apply to any kind but are
                  primarily meaningful on the Custom webhook card. */}
              <Field label="Headers (JSON, optional)">
                <textarea
                  value={headersStr}
                  onChange={(e) => setHeadersStr(e.target.value)}
                  rows={3}
                  placeholder='{"Authorization": "Bearer ${TOKEN}"}'
                  className="w-full rounded-md border border-border bg-bg p-2 font-mono text-xs"
                />
                <p className="mt-1 text-xs text-muted-fg">
                  For Custom webhook only. <code>${"{VAR}"}</code> expands
                  from the container's environment.
                </p>
              </Field>
              <Field label="Payload template (JSON, optional)">
                <textarea
                  value={payloadStr}
                  onChange={(e) => setPayloadStr(e.target.value)}
                  rows={4}
                  placeholder='{"text": "{message}"}'
                  className="w-full rounded-md border border-border bg-bg p-2 font-mono text-xs"
                />
                <p className="mt-1 text-xs text-muted-fg">
                  For Custom webhook only. First-class kinds ignore this.
                </p>
              </Field>
            </div>
          )}
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}
      </div>

      <div className="mt-6 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </Button>
      </div>
    </Dialog>
  );
}

// ------------------------------------------------------------------ //
// Per-kind field blocks
// ------------------------------------------------------------------ //

function getConfig<T extends Record<string, unknown>>(d: Draft): T {
  return (d.config ?? {}) as T;
}

function DiscordFields({
  d,
  setD,
}: {
  d: Draft;
  setD: (d: Draft) => void;
}) {
  return (
    <Field label="Webhook URL">
      <Input
        value={d.url}
        placeholder="https://discord.com/api/webhooks/..."
        onChange={(e) => setD({ ...d, url: e.target.value })}
      />
    </Field>
  );
}

type HaConfig = {
  base_url?: string;
  access_token?: string;
  mode?: "notify" | "webhook";
  service?: string;
  webhook_id?: string;
  title?: string;
};

function HaFields({ d, setD }: { d: Draft; setD: (d: Draft) => void }) {
  const c = getConfig<HaConfig>(d);
  const mode = c.mode ?? "notify";
  const setCfg = (patch: Partial<HaConfig>) =>
    setD({ ...d, config: { ...c, ...patch } as Record<string, unknown> });

  return (
    <>
      <Field label="Home Assistant base URL">
        <Input
          value={c.base_url ?? ""}
          placeholder="https://homeassistant.local:8123"
          onChange={(e) => setCfg({ base_url: e.target.value })}
        />
      </Field>
      <Field label="Long-lived access token">
        <SecretInput
          value={c.access_token ?? ""}
          onChange={(v) => setCfg({ access_token: v })}
          placeholder="eyJhbGciOi..."
        />
        <p className="mt-1 text-xs text-muted-fg">
          Profile → Security → Long-Lived Access Tokens in Home Assistant.
        </p>
      </Field>
      <Field label="Mode">
        <div className="flex gap-2">
          <ModeRadio
            checked={mode === "notify"}
            onClick={() => setCfg({ mode: "notify" })}
            label="notify service"
            hint="Call notify.mobile_app_x or similar"
          />
          <ModeRadio
            checked={mode === "webhook"}
            onClick={() => setCfg({ mode: "webhook" })}
            label="webhook trigger"
            hint="Fire an automation webhook"
          />
        </div>
      </Field>
      {mode === "notify" ? (
        <Field label="Notify service">
          <Input
            value={c.service ?? ""}
            placeholder="notify.mobile_app_pixel"
            onChange={(e) => setCfg({ service: e.target.value })}
          />
          <p className="mt-1 text-xs text-muted-fg">
            The full dotted service name, without the /api/services/ prefix.
          </p>
        </Field>
      ) : (
        <Field label="Webhook ID">
          <Input
            value={c.webhook_id ?? ""}
            placeholder="pfsense-backup-event"
            onChange={(e) => setCfg({ webhook_id: e.target.value })}
          />
        </Field>
      )}
      <Field label="Title (optional)">
        <Input
          value={c.title ?? ""}
          placeholder="pfSense Backup"
          onChange={(e) => setCfg({ title: e.target.value })}
        />
      </Field>
    </>
  );
}

type NtfyConfig = {
  server_url?: string;
  topic?: string;
  auth_token?: string;
  priority?: number;
  tags?: string[];
};

function NtfyFields({ d, setD }: { d: Draft; setD: (d: Draft) => void }) {
  const c = getConfig<NtfyConfig>(d);
  const setCfg = (patch: Partial<NtfyConfig>) =>
    setD({ ...d, config: { ...c, ...patch } as Record<string, unknown> });
  const tagsStr = (c.tags ?? []).join(", ");
  return (
    <>
      <Field label="Server URL">
        <Input
          value={c.server_url ?? "https://ntfy.sh"}
          placeholder="https://ntfy.sh"
          onChange={(e) => setCfg({ server_url: e.target.value })}
        />
      </Field>
      <Field label="Topic">
        <Input
          value={c.topic ?? ""}
          placeholder="my-pfsense-alerts"
          onChange={(e) => setCfg({ topic: e.target.value })}
        />
      </Field>
      <Field label="Auth token (optional)">
        <SecretInput
          value={c.auth_token ?? ""}
          onChange={(v) => setCfg({ auth_token: v })}
          placeholder="tk_..."
        />
      </Field>
      <Field label="Priority">
        <select
          value={c.priority ?? 3}
          onChange={(e) => setCfg({ priority: Number(e.target.value) })}
          className="h-9 w-full rounded-md border border-border bg-bg px-2 text-sm"
        >
          <option value={1}>1 — min</option>
          <option value={2}>2 — low</option>
          <option value={3}>3 — default</option>
          <option value={4}>4 — high</option>
          <option value={5}>5 — max</option>
        </select>
      </Field>
      <Field label="Tags (comma-separated, optional)">
        <Input
          value={tagsStr}
          placeholder="warning, computer"
          onChange={(e) =>
            setCfg({
              tags: e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
            })
          }
        />
      </Field>
    </>
  );
}

type HcConfig = {
  provisioned?: boolean;
  server_url?: string;
  api_key?: string;
  uuid?: string;
  expected_timeout?: number;
  grace?: number;
};

function HcFields({ d, setD }: { d: Draft; setD: (d: Draft) => void }) {
  const c = getConfig<HcConfig>(d);
  const provisioned = !!c.provisioned;
  const setCfg = (patch: Partial<HcConfig> | null) =>
    setD({
      ...d,
      config: patch === null ? null : ({ ...c, ...patch } as Record<string, unknown>),
    });

  return (
    <>
      <Field label="Mode">
        <div className="flex gap-2">
          <ModeRadio
            checked={!provisioned}
            onClick={() => setCfg(null)}
            label="Manual"
            hint="Paste the ping URL from the Healthchecks dashboard"
          />
          <ModeRadio
            checked={provisioned}
            onClick={() =>
              setCfg({
                provisioned: true,
                server_url: c.server_url ?? "https://healthchecks.io",
                api_key: c.api_key ?? "",
                expected_timeout: c.expected_timeout ?? 86400,
                grace: c.grace ?? 3600,
              })
            }
            label="Auto-provision"
            hint="We create the check for you via the API"
          />
        </div>
      </Field>

      {!provisioned ? (
        <Field label="Ping URL">
          <Input
            value={d.url}
            placeholder="https://hc-ping.com/<uuid> or https://checks.example.com/ping/<slug>"
            onChange={(e) => setD({ ...d, url: e.target.value })}
          />
          <p className="mt-1 text-xs text-muted-fg">
            Success pings the base URL; failure pings <code>/fail</code>;
            each run starts with a <code>/start</code> ping for duration
            tracking.
          </p>
        </Field>
      ) : (
        <>
          <Field label="Healthchecks server URL">
            <Input
              value={c.server_url ?? ""}
              placeholder="https://healthchecks.io"
              onChange={(e) => setCfg({ server_url: e.target.value })}
            />
          </Field>
          <Field label="Project API key (write permission)">
            <SecretInput
              value={c.api_key ?? ""}
              onChange={(v) => setCfg({ api_key: v })}
              placeholder="..."
            />
            <p className="mt-1 text-xs text-muted-fg">
              Healthchecks dashboard → Project Settings → API Keys. Stored
              encrypted only if your DB volume is.
            </p>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Expected interval (seconds)">
              <Input
                type="number"
                value={c.expected_timeout ?? 86400}
                onChange={(e) =>
                  setCfg({ expected_timeout: Number(e.target.value) })
                }
              />
              <p className="mt-1 text-xs text-muted-fg">Default: 86400 (24h).</p>
            </Field>
            <Field label="Grace period (seconds)">
              <Input
                type="number"
                value={c.grace ?? 3600}
                onChange={(e) => setCfg({ grace: Number(e.target.value) })}
              />
              <p className="mt-1 text-xs text-muted-fg">Default: 3600 (1h).</p>
            </Field>
          </div>
          {c.uuid && (
            <div className="rounded-md border border-border bg-muted/10 p-2 text-xs text-muted-fg">
              Check created — uuid <code>{c.uuid}</code>
            </div>
          )}
        </>
      )}
    </>
  );
}

function WebhookFields({ d, setD }: { d: Draft; setD: (d: Draft) => void }) {
  return (
    <Field label="URL">
      <Input
        value={d.url}
        placeholder="https://example.com/webhook"
        onChange={(e) => setD({ ...d, url: e.target.value })}
      />
      <p className="mt-1 text-xs text-muted-fg">
        Headers and payload template live under Advanced below.
      </p>
    </Field>
  );
}

// ------------------------------------------------------------------ //
// Small shared widgets
// ------------------------------------------------------------------ //

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <Label>{label}</Label>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function ModeRadio({
  checked,
  onClick,
  label,
  hint,
}: {
  checked: boolean;
  onClick: () => void;
  label: string;
  hint: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex-1 rounded-md border p-2 text-left text-sm transition-colors",
        checked
          ? "border-accent bg-accent/10 text-accent"
          : "border-border bg-muted/20 text-muted-fg hover:text-fg",
      )}
    >
      <div className="font-medium">{label}</div>
      <div className="mt-0.5 text-xs text-muted-fg">{hint}</div>
    </button>
  );
}

function SecretInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  const [visible, setVisible] = useState(false);
  const isSavedPlaceholder = value === "__set__";
  return (
    <div className="flex gap-1">
      <Input
        type={visible || isSavedPlaceholder ? "text" : "password"}
        value={isSavedPlaceholder ? "" : value}
        placeholder={isSavedPlaceholder ? "(saved — leave blank to keep)" : placeholder}
        onChange={(e) => onChange(e.target.value || (isSavedPlaceholder ? "__set__" : ""))}
      />
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={() => setVisible((v) => !v)}
        title={visible ? "Hide" : "Show"}
      >
        {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </Button>
    </div>
  );
}

function InstanceScopeField({
  value,
  instances,
  onChange,
}: {
  value: number[] | null;
  instances: Instance[];
  onChange: (v: number[] | null) => void;
}) {
  const selected = value ?? [];
  const selectedSet = new Set(selected);
  const available = instances.filter((i) => !selectedSet.has(i.id));
  return (
    <Field label="Instance scope">
      <div className="flex flex-wrap items-center gap-2">
        {selected.length === 0 ? (
          <span className="text-xs text-muted-fg">All instances (default)</span>
        ) : (
          selected.map((id) => {
            const inst = instances.find((i) => i.id === id);
            const label = inst?.name ?? `id=${id}`;
            return (
              <span
                key={id}
                className="inline-flex items-center gap-1 rounded-full border border-accent/50 bg-accent/10 px-2 py-0.5 text-xs text-accent"
              >
                {label}
                <button
                  type="button"
                  onClick={() => {
                    const next = selected.filter((x) => x !== id);
                    onChange(next.length === 0 ? null : next);
                  }}
                  className="ml-1 text-accent/70 hover:text-accent"
                  aria-label={`Remove ${label}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            );
          })
        )}
        {available.length > 0 && (
          <select
            value=""
            onChange={(e) => {
              const id = Number(e.target.value);
              if (!Number.isFinite(id)) return;
              onChange([...selected, id]);
            }}
            className="h-7 rounded-md border border-border bg-bg px-2 text-xs text-muted-fg"
          >
            <option value="">+ add instance</option>
            {available.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name}
              </option>
            ))}
          </select>
        )}
      </div>
      <p className="mt-1 text-xs text-muted-fg">
        Leave blank to notify for every instance. Select one or more to
        only notify when those instances run.
      </p>
    </Field>
  );
}
