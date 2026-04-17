import { Suspense, lazy, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { api } from "@/api/client";

const MonacoDiff = lazy(() => import("@/components/MonacoDiff"));

interface Pair {
  a: { id: number; filename: string; started_at: string; content: string };
  b: { id: number; filename: string; started_at: string; content: string };
}

export function BackupDiffPage() {
  const { a, b } = useParams();
  const [pair, setPair] = useState<Pair | null>(null);
  const [error, setError] = useState<string | null>(null);

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
  if (!pair) return <div className="p-6 text-sm text-muted-fg">Loading…</div>;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border pb-3">
        <div>
          <Link to="/backups" className="inline-flex items-center gap-1 text-sm text-muted-fg hover:text-accent">
            <ArrowLeft className="h-4 w-4" /> back to backups
          </Link>
          <h1 className="text-xl font-semibold">Compare backups</h1>
        </div>
        <div className="text-right text-xs text-muted-fg">
          <div>A: {pair.a.filename}</div>
          <div>B: {pair.b.filename}</div>
        </div>
      </div>

      <div className="mt-3 flex-1 overflow-hidden rounded border border-border">
        <Suspense fallback={<div className="p-6 text-sm text-muted-fg">Loading diff editor…</div>}>
          <MonacoDiff original={pair.a.content} modified={pair.b.content} />
        </Suspense>
      </div>
    </div>
  );
}
