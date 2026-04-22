import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { useParsedBackup } from "@/api/queries";
import {
  blameTooltipText,
  useAnchorBlame,
} from "@/components/xref/AnchorBlame";

const MonacoViewer = lazy(() => import("@/components/MonacoViewer"));

/**
 * Self-contained Raw XML viewer. Shared between
 * ``BackupView`` (which already fetches its own XML for
 * copy/download and passes it in) and
 * ``InstanceHistory`` (which fetches on-demand per focused backup).
 *
 * Reads the blame summary from ``AnchorBlameProvider`` context —
 * callers that want Monaco hover cards wrap this in a provider at a
 * higher level. No prop for blame data since both current callers
 * already do that for the Structured side.
 */
export function RawXmlPanel({
  backupId,
  content: externalContent,
  focusLine,
  onCursorAnchorChange,
}: {
  backupId: number;
  /** If the caller already has the XML (BackupView does for
   *  copy/download), pass it to skip the internal fetch. */
  content?: string;
  focusLine?: number;
  onCursorAnchorChange?: (anchor: string | null) => void;
}) {
  const { data: parsedResponse } = useParsedBackup(backupId);
  const positions = parsedResponse?.positions;
  const blame = useAnchorBlame();

  // Internal fetch path — only runs when no external content is
  // supplied. A ``null`` state + effect mirrors how BackupView does
  // it so failure handling is consistent.
  const [fetched, setFetched] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  useEffect(() => {
    if (externalContent !== undefined) return;
    let cancelled = false;
    setFetched(null);
    setFetchError(null);
    fetch(`/api/backups/${backupId}/content`, { credentials: "include" })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.text();
      })
      .then((text) => {
        if (!cancelled) setFetched(text);
      })
      .catch((e) => {
        if (!cancelled) setFetchError(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [backupId, externalContent]);

  const content = externalContent ?? fetched;

  const anchorForLine = useCallback(
    (line: number): string | null => {
      if (!positions) return null;
      let best: string | null = null;
      let bestSpan = Infinity;
      for (const [id, range] of Object.entries(positions)) {
        const [start, end] = range;
        if (start <= line && line <= end) {
          const span = end - start;
          if (span < bestSpan) {
            bestSpan = span;
            best = id;
          }
        }
      }
      return best;
    },
    [positions],
  );

  const monacoBlameProvider = useCallback(
    (line: number): string | null => {
      if (!blame?.indexed || !blame.anchors) return null;
      const anchor = anchorForLine(line);
      if (!anchor) return null;
      const entry = blame.anchors[anchor];
      if (!entry) return null;
      return blameTooltipText(entry);
    },
    [anchorForLine, blame],
  );

  const onMonacoCursorLine = useCallback(
    (line: number) => {
      if (!onCursorAnchorChange) return;
      onCursorAnchorChange(anchorForLine(line));
    },
    [anchorForLine, onCursorAnchorChange],
  );

  if (fetchError) {
    return <div className="p-6 text-sm text-danger">{fetchError}</div>;
  }
  if (content === null || content === undefined) {
    return <div className="p-6 text-sm text-muted-fg">Loading XML…</div>;
  }

  return (
    <Suspense
      fallback={<div className="p-6 text-sm text-muted-fg">Loading editor…</div>}
    >
      <MonacoViewer
        content={content}
        focusLine={focusLine}
        onCursorLineChange={onCursorAnchorChange ? onMonacoCursorLine : undefined}
        blameProvider={monacoBlameProvider}
      />
    </Suspense>
  );
}
