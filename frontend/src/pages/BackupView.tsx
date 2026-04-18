import { Suspense, lazy, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Check,
  ClipboardCopy,
  Download,
  Pencil,
  Split,
  Tag as TagIcon,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useToast } from "@/components/ui/Toast";
import { useBackups, useInstances, useUpdateBackup } from "@/api/queries";
import { api, triggerDownload } from "@/api/client";

const MonacoViewer = lazy(() => import("@/components/MonacoViewer"));

interface BackupDetail {
  id: number;
  instance_id: number;
  started_at: string;
  finished_at: string;
  duration_seconds: number;
  filename: string;
  path: string;
  size_bytes: number;
  compressed: boolean;
  success: boolean;
  error_message: string | null;
  tag: string | null;
  note: string | null;
}

export function BackupViewPage() {
  const { id: idParam } = useParams();
  const id = Number(idParam);
  const nav = useNavigate();
  const toast = useToast();

  const [detail, setDetail] = useState<BackupDetail | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const instances = useInstances();
  // Pull the sibling list AFTER we know which instance this backup belongs to
  // so "Diff against previous" can find the immediate predecessor.
  const siblings = useBackups(detail?.instance_id);
  const updateBackup = useUpdateBackup();

  const [editingMeta, setEditingMeta] = useState(false);
  const [tagDraft, setTagDraft] = useState("");
  const [noteDraft, setNoteDraft] = useState("");

  useEffect(() => {
    let cancelled = false;
    setDetail(null);
    setContent(null);
    setError(null);
    Promise.all([
      api.get<BackupDetail>(`/api/backups/${id}`),
      fetch(`/api/backups/${id}/content`, { credentials: "include" }).then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.text();
      }),
    ])
      .then(([d, c]) => {
        if (cancelled) return;
        setDetail(d);
        setContent(c);
      })
      .catch((e) => !cancelled && setError(String(e)));
    return () => {
      cancelled = true;
    };
  }, [id]);

  const instanceName = useMemo(() => {
    if (!detail) return "";
    const inst = instances.data?.find((i) => i.id === detail.instance_id);
    return inst?.name ?? `id=${detail.instance_id}`;
  }, [instances.data, detail]);

  const previous = useMemo(() => {
    if (!detail || !siblings.data) return null;
    const olderFirst = siblings.data
      .filter((b) => b.id !== detail.id && b.success)
      .filter((b) => new Date(b.started_at) < new Date(detail.started_at))
      .sort((a, b) => (new Date(b.started_at).getTime() - new Date(a.started_at).getTime()));
    return olderFirst[0] ?? null;
  }, [detail, siblings.data]);

  async function copyToClipboard() {
    if (!content) return;
    try {
      await navigator.clipboard.writeText(content);
      toast.success("Copied XML to clipboard");
    } catch (e) {
      toast.error(String(e));
    }
  }

  async function download() {
    if (!detail) return;
    const blob = await api.downloadBlob(`/api/backups/${detail.id}/download`);
    triggerDownload(blob, detail.filename);
  }

  function startEditingMeta() {
    if (!detail) return;
    setTagDraft(detail.tag ?? "");
    setNoteDraft(detail.note ?? "");
    setEditingMeta(true);
  }

  async function saveMeta() {
    if (!detail) return;
    try {
      const r = await updateBackup.mutateAsync({
        id: detail.id,
        patch: { tag: tagDraft, note: noteDraft },
      });
      setDetail({ ...detail, tag: r.tag, note: r.note });
      setEditingMeta(false);
      toast.success("Saved tag / note");
    } catch {
      // MutationCache's onError already surfaces the error toast.
    }
  }

  if (error) return <div className="p-6 text-sm text-danger">{error}</div>;
  if (!detail || content === null)
    return <div className="p-6 text-sm text-muted-fg">Loading…</div>;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start justify-between gap-4 border-b border-border pb-3">
        <div className="min-w-0">
          <Link
            to="/backups"
            className="inline-flex items-center gap-1 text-sm text-muted-fg hover:text-accent"
          >
            <ArrowLeft className="h-4 w-4" /> back to backups
          </Link>
          <h1 className="mt-1 text-xl font-semibold">
            {instanceName}{" "}
            <span className="text-muted-fg font-normal">
              · {new Date(detail.started_at).toLocaleString()}
            </span>
          </h1>
          <div className="mt-1 flex items-center gap-2 font-mono text-xs text-muted-fg">
            <span className="truncate">{detail.filename}</span>
            {detail.compressed && <Badge tone="muted">gz</Badge>}
            <span>·</span>
            <span>{Math.round(detail.size_bytes / 1024)} KB</span>
            <span>·</span>
            <span>{detail.duration_seconds.toFixed(1)}s</span>
            {detail.tag && !editingMeta && (
              <span className="inline-flex items-center gap-1 rounded-full border border-accent/50 bg-accent/10 px-2 py-0.5 text-xs text-accent">
                <TagIcon className="h-3 w-3" />
                {detail.tag}
              </span>
            )}
          </div>
          {detail.note && !editingMeta && (
            <p className="mt-2 max-w-2xl whitespace-pre-wrap text-sm text-muted-fg">
              {detail.note}
            </p>
          )}
          {editingMeta && (
            <div className="mt-3 flex max-w-2xl flex-col gap-2">
              <Input
                value={tagDraft}
                onChange={(e) => setTagDraft(e.target.value)}
                placeholder="Tag (e.g. pre-upgrade, known-good)"
                maxLength={64}
                aria-label="Tag"
              />
              <textarea
                value={noteDraft}
                onChange={(e) => setNoteDraft(e.target.value)}
                placeholder="Free-text note (what makes this backup interesting?)"
                rows={3}
                className="w-full rounded-md border border-border bg-bg p-2 text-sm"
                aria-label="Note"
              />
              <div className="flex gap-2">
                <Button size="sm" onClick={saveMeta} disabled={updateBackup.isPending}>
                  <Check className="h-4 w-4" /> Save
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setEditingMeta(false)}
                  disabled={updateBackup.isPending}
                >
                  <X className="h-4 w-4" /> Cancel
                </Button>
              </div>
            </div>
          )}
        </div>
        <div className="flex shrink-0 gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={startEditingMeta}
            disabled={editingMeta}
            title="Edit tag / note"
          >
            <Pencil className="h-4 w-4" />
            Tag / note
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => previous && nav(`/backups/diff/${previous.id}/${detail.id}`)}
            disabled={!previous}
            title={
              previous
                ? `Diff against ${new Date(previous.started_at).toLocaleString()}`
                : "No prior successful backup for this instance"
            }
          >
            <Split className="h-4 w-4" />
            Diff vs previous
          </Button>
          <Button variant="secondary" size="sm" onClick={copyToClipboard}>
            <ClipboardCopy className="h-4 w-4" />
            Copy
          </Button>
          <Button size="sm" onClick={download}>
            <Download className="h-4 w-4" />
            Download
          </Button>
        </div>
      </div>

      <div className="mt-3 flex-1 overflow-hidden rounded border border-border">
        <Suspense
          fallback={<div className="p-6 text-sm text-muted-fg">Loading editor…</div>}
        >
          <MonacoViewer content={content} />
        </Suspense>
      </div>
    </div>
  );
}
