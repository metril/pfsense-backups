import { Suspense, lazy, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { Tabs } from "@/components/ui/Tabs";
import { ReturnToBackupPill } from "@/components/nav/ReturnToBackupPill";
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
  const [searchParams] = useSearchParams();
  // ``?from=<id>`` marks the backup the operator was viewing before
  // clicking "Diff vs previous" (BackupView / InstanceHistory
  // entrypoints set this; the ``Backups`` list multi-select does
  // not). Regex-guard the number parse so a junk ``?from=foo`` from
  // a hand-edited URL doesn't render a ``#NaN`` back link.
  const fromRaw = searchParams.get("from");
  const fromId =
    fromRaw && /^\d+$/.test(fromRaw) ? Number(fromRaw) : null;
  const [pair, setPair] = useState<Pair | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<DiffTab>("structured");

  const fromFilename =
    fromId === aId
      ? pair?.a.filename
      : fromId === bId
        ? pair?.b.filename
        : null;

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
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <Link
              to="/backups"
              className="inline-flex items-center gap-1 text-sm text-muted-fg hover:text-accent"
            >
              <ArrowLeft className="h-4 w-4" /> Back to backups
            </Link>
            {fromId !== null && (
              <Link
                to={`/backups/${fromId}/view`}
                className="inline-flex items-center gap-1 text-sm text-muted-fg hover:text-accent"
              >
                <ArrowLeft className="h-4 w-4" />
                Back to{" "}
                <span className="font-mono">
                  {fromFilename ?? `#${fromId}`}
                </span>
              </Link>
            )}
          </div>
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
          // Single shared panel — we omit aria-controls on tabs so
          // SRs don't announce a bogus 1:1 tab↔panel association.
          { id: "structured", label: "Structured" },
          { id: "raw", label: "Raw XML" },
        ]}
      />

      <div
        id="backup-diff-panel"
        role="tabpanel"
        tabIndex={0}
        aria-labelledby={`backup-diff-tab-${tab}`}
        className="flex-1 overflow-hidden rounded-b border border-t-0 border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
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
      {fromId !== null && <ReturnToBackupPill fromBackupId={fromId} />}
    </div>
  );
}
