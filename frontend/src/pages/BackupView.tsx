import { Suspense, lazy, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ClipboardCopy, Download, Split } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import { useBackups, useInstances } from "@/api/queries";
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
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
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
