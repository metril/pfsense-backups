import { useState } from "react";
import { BellRing, Pencil, Plus, Send, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import {
  useCreateNotification,
  useDeleteNotification,
  useNotifications,
  useSendTestNotification,
  useUpdateNotification,
} from "@/api/queries";
import type { Notification } from "@/api/types";

type Draft = Omit<Notification, "id"> & { id?: number };

const blank = (): Draft => ({
  name: "",
  url: "",
  trigger: "always",
  enabled: true,
  message_format: "{status}: pfSense backup completed. {details}",
  include_instance_details: true,
  timeout_seconds: 10,
  headers: null,
  payload_template: null,
});

export function NotificationsPage() {
  const { data, isPending } = useNotifications();
  const create = useCreateNotification();
  const update = useUpdateNotification();
  const del = useDeleteNotification();
  const send = useSendTestNotification();
  const [editing, setEditing] = useState<Draft | null>(null);

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Notifications</h1>
        <Button onClick={() => setEditing(blank())}>
          <Plus className="h-4 w-4" /> Add webhook
        </Button>
      </div>

      {isPending ? (
        <div className="mt-6 text-sm text-muted-fg">Loading…</div>
      ) : (
        <div className="mt-6 space-y-3">
          {data!.map((n) => (
            <div key={n.id} className="flex items-center gap-4 rounded-lg border border-border bg-muted/20 p-4">
              <BellRing className="h-5 w-5 text-muted-fg" />
              <div className="flex-1 min-w-0">
                <div className="font-medium">{n.name}</div>
                <div className="truncate font-mono text-xs text-muted-fg">{n.url}</div>
              </div>
              <Badge tone={n.enabled ? "success" : "muted"}>{n.trigger}</Badge>
              <div className="flex gap-1">
                <Button variant="ghost" size="icon" onClick={() => send.mutate(n.id)} title="Send test">
                  <Send className="h-4 w-4" />
                </Button>
                <Button variant="ghost" size="icon" onClick={() => setEditing({ ...n })}>
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => {
                    if (confirm(`Delete ${n.name}?`)) del.mutate(n.id);
                  }}
                >
                  <Trash2 className="h-4 w-4 text-danger" />
                </Button>
              </div>
            </div>
          ))}
          {data!.length === 0 && (
            <div className="rounded-lg border border-border bg-muted/20 p-8 text-center text-sm text-muted-fg">
              No webhooks configured.
            </div>
          )}
        </div>
      )}

      {editing && (
        <EditorDialog
          draft={editing}
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

function stripId(d: Draft): Omit<Notification, "id"> {
  const { id: _id, ...rest } = d;
  void _id;
  return rest;
}

function EditorDialog({ draft, onClose, onSave }: { draft: Draft; onClose: () => void; onSave: (d: Draft) => Promise<void> }) {
  const [d, setD] = useState(draft);
  const [headersStr, setHeadersStr] = useState(d.headers ? JSON.stringify(d.headers, null, 2) : "");
  const [payloadStr, setPayloadStr] = useState(d.payload_template ? JSON.stringify(d.payload_template, null, 2) : "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

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
    <Dialog open onOpenChange={(o) => !o && onClose()} title={d.id === undefined ? "Add webhook" : `Edit ${d.name}`}>
      <div className="space-y-3">
        <Field label="Name"><Input value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} /></Field>
        <Field label="URL"><Input value={d.url} onChange={(e) => setD({ ...d, url: e.target.value })} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Trigger">
            <select
              value={d.trigger}
              onChange={(e) => setD({ ...d, trigger: e.target.value as Draft["trigger"] })}
              className="h-9 w-full rounded-md border border-border bg-bg px-2 text-sm"
            >
              <option value="always">always</option>
              <option value="success">success</option>
              <option value="failure">failure</option>
            </select>
          </Field>
          <Field label="Timeout (s)"><Input type="number" value={d.timeout_seconds} onChange={(e) => setD({ ...d, timeout_seconds: Number(e.target.value) })} /></Field>
        </div>
        <Field label="Message format">
          <Input value={d.message_format} onChange={(e) => setD({ ...d, message_format: e.target.value })} />
        </Field>

        <Field label="Headers (JSON, optional)">
          <textarea
            value={headersStr}
            onChange={(e) => setHeadersStr(e.target.value)}
            rows={3}
            className="w-full rounded-md border border-border bg-bg p-2 font-mono text-xs"
          />
        </Field>
        <Field label="Payload template (JSON, optional)">
          <textarea
            value={payloadStr}
            onChange={(e) => setPayloadStr(e.target.value)}
            rows={4}
            className="w-full rounded-md border border-border bg-bg p-2 font-mono text-xs"
          />
        </Field>

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={d.enabled} onChange={(e) => setD({ ...d, enabled: e.target.checked })} /> enabled
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={d.include_instance_details} onChange={(e) => setD({ ...d, include_instance_details: e.target.checked })} /> include instance details
        </label>

        {error && <p className="text-sm text-danger">{error}</p>}
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
