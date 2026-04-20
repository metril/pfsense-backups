import { Suspense, lazy, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { Tabs } from "@/components/ui/Tabs";
import { api } from "@/api/client";

const MonacoDiff = lazy(() => import("@/components/MonacoDiff"));
const ParsedBackupDiff = lazy(() =>
  import("@/components/ParsedBackupDiff").then((m) => ({
    default: m.ParsedBackupDiff,
  })),
);

interface Pair {
  a: { id: number; filename: string; started_at: string; content: string };
  b: { id: number; filename: string; started_at: string; content: string };
}

type DiffTab = "structured" | "raw";

export function BackupDiffPage() {
  const { a, b } = useParams();
  const aId = Number(a);
  const bId = Number(b);
  const [pair, setPair] = useState<Pair | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<DiffTab>("structured");

  // Raw content is only needed when the user flips to the "Raw XML" tab,
  // but we fetch eagerly so the toggle is instantaneous. The structured
  // tab has its own fetch (via useParsedDiffPair) and renders first.
  useEffect(() => {
    let cancelled = false;
    api
      .get<Pair>(`/api/backups/diff/pair?a=${a}&b=${b}`)
      .then((p) => !cancelled && setPair(p))
      .catch((e) => !cancelled && setError(String(e)));
    return () => {
      cancelled = true;
    };
  }, [a, b]);

  if (error) return <div className="p-6 text-sm text-danger">{error}</div>;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border pb-3">
        <div>
          <Link
            to="/backups"
            className="inline-flex items-center gap-1 text-sm text-muted-fg hover:text-accent"
          >
            <ArrowLeft className="h-4 w-4" /> back to backups
          </Link>
          <h1 className="text-xl font-semibold">Compare backups</h1>
        </div>
        <div className="text-right text-xs text-muted-fg">
          <div>A: {pair?.a.filename ?? `#${a}`}</div>
          <div>B: {pair?.b.filename ?? `#${b}`}</div>
        </div>
      </div>

      <Tabs
        className="mt-3"
        value={tab}
        onChange={(id) => setTab(id as DiffTab)}
        ariaLabel="Diff view"
        idPrefix="backup-diff"
        items={[
          { id: "structured", label: "Structured", panelId: "backup-diff-panel" },
          { id: "raw", label: "Raw XML", panelId: "backup-diff-panel" },
        ]}
      />

      <div
        id="backup-diff-panel"
        role="tabpanel"
        aria-labelledby={`backup-diff-tab-${tab}`}
        className="flex-1 overflow-hidden rounded-b border border-t-0 border-border"
      >
        <Suspense
          fallback={<div className="p-6 text-sm text-muted-fg">Loading…</div>}
        >
          {tab === "structured" ? (
            <ParsedBackupDiff a={aId} b={bId} />
          ) : !pair ? (
            <div className="p-6 text-sm text-muted-fg">Loading raw XML…</div>
          ) : (
            <MonacoDiff
              original={pair.a.content}
              modified={pair.b.content}
            />
          )}
        </Suspense>
      </div>
    </div>
  );
}
