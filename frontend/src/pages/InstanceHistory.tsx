import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ChevronLeft, ChevronRight, Clock, Split } from "lucide-react";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import {
  useBackups,
  useInstances,
  useParsedDiffPair,
} from "@/api/queries";
import { collectChangedAnchors } from "@/lib/changedAnchors";
import { useFocusedAnchor } from "@/lib/useFocusedAnchor";
import { AnchorHistoryDrawer } from "@/components/xref/AnchorHistoryDrawer";

const ParsedBackupView = lazy(() =>
  import("@/components/ParsedBackupView").then((m) => ({
    default: m.ParsedBackupView,
  })),
);

/**
 * Historical-diff timeline for a single pfSense instance.
 *
 * The timeline renders every successful backup for the instance as a
 * tick on a horizontal slider. Scrubbing (← / → / click a tick /
 * drag the input) updates the focused backup; the Structured view
 * re-renders for that backup. A "vs previous" toggle pulls the
 * backup-pair diff and marks every row / field that changed with
 * ``data-xref-changed="true"`` so ``index.css`` paints it.
 *
 * The diff overlay piggybacks on the existing ``ParsedBackupView``
 * DOM — we don't fork the renderer. An effect walks the current set
 * of ``id`` elements and toggles the attribute whenever the diff
 * changes; because ``ParsedBackupView`` re-mounts on backup change
 * we re-run the effect after a ``requestAnimationFrame`` to make
 * sure the new tree has painted.
 */
export function InstanceHistoryPage() {
  const { id: idParam } = useParams();
  const id = Number(idParam);
  const nav = useNavigate();

  const instances = useInstances();
  const instance = instances.data?.find((i) => i.id === id);

  // Load all successful backups in chronological (ascending) order
  // so array indexes map directly onto "earlier → later" on the
  // timeline.
  const backupsQuery = useBackups({
    instanceId: id,
    sort: "started_at",
    order: "asc",
  });
  // Filter out failed backups. Use the raw query data as the only
  // dep so we don't pay for a fresh filter on every render.
  const backups = useMemo(
    () => (backupsQuery.data ?? []).filter((b) => b.success),
    [backupsQuery.data],
  );

  const [focusIdx, setFocusIdx] = useState<number>(-1);
  // Initialise to the latest backup on first load; re-initialise
  // only when the list itself grows (new backup arrived during
  // session) so we don't stomp the operator's scrub position on
  // refetch.
  useEffect(() => {
    if (focusIdx < 0 && backups.length > 0) {
      setFocusIdx(backups.length - 1);
    }
  }, [backups.length, focusIdx]);

  const focused = focusIdx >= 0 ? backups[focusIdx] : undefined;
  const previous = focusIdx > 0 ? backups[focusIdx - 1] : undefined;

  // Diff against the previous backup. Enabled whenever we have both
  // sides; the hook already handles the null case.
  const diffQuery = useParsedDiffPair(
    previous?.id ?? null,
    focused?.id ?? null,
  );
  const changedAnchors = useMemo(
    () => (diffQuery.data ? collectChangedAnchors(diffQuery.data) : new Set<string>()),
    [diffQuery.data],
  );

  // Apply ``data-xref-changed`` to every anchor in the changed set.
  // Run after a frame so the Structured view's lazy-mount + React
  // commit have painted.
  useEffect(() => {
    let cancelled = false;
    const apply = () => {
      if (cancelled) return;
      document
        .querySelectorAll<HTMLElement>("[data-xref-changed]")
        .forEach((el) => el.removeAttribute("data-xref-changed"));
      for (const anchor of changedAnchors) {
        const el = document.getElementById(anchor);
        if (el) el.setAttribute("data-xref-changed", "true");
      }
    };
    const rafId = requestAnimationFrame(() => {
      // Double-RAF so Suspense has a second frame to reveal the
      // lazily-imported ``ParsedBackupView`` after a backup switch.
      requestAnimationFrame(apply);
    });
    return () => {
      cancelled = true;
      cancelAnimationFrame(rafId);
    };
  }, [changedAnchors, focused?.id]);

  // Keyboard ← / → steps through the timeline. Home / End jump to
  // edges. Guards against typing into inputs / modals, mirroring
  // the global pattern used by ExpandCollapseAll and QuickJump.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      if (target?.closest('[role="dialog"], [role="listbox"], [role="menu"]'))
        return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        setFocusIdx((i) => Math.max(0, i - 1));
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        setFocusIdx((i) => Math.min(backups.length - 1, i + 1));
      } else if (e.key === "Home") {
        e.preventDefault();
        setFocusIdx(0);
      } else if (e.key === "End") {
        e.preventDefault();
        setFocusIdx(backups.length - 1);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [backups.length]);

  const onSliderChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setFocusIdx(Number(e.target.value));
    },
    [],
  );

  // ------- Blame drawer (v0.24.0) ----------------------------------
  // ``useFocusedAnchor`` tracks the nearest visible row / field in
  // the Structured view. Pressing ``h`` (outside inputs / modals)
  // opens the AnchorHistoryDrawer for whatever is focused; ``Esc``
  // closes it (handled inside the drawer).
  const focusedAnchor = useFocusedAnchor(true);
  const [blameAnchor, setBlameAnchor] = useState<string | null>(null);
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      if (target?.closest('[role="dialog"], [role="listbox"], [role="menu"]'))
        return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "h" && focusedAnchor) {
        e.preventDefault();
        setBlameAnchor(focusedAnchor);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [focusedAnchor]);

  if (!Number.isFinite(id)) {
    return (
      <div className="p-6">
        <Alert tone="danger" title="Bad instance id">{idParam}</Alert>
      </div>
    );
  }

  if (backupsQuery.isLoading) {
    return <div className="p-6 text-sm text-muted-fg">Loading backups…</div>;
  }

  if (backups.length === 0) {
    return (
      <div className="p-6">
        <Alert
          tone="info"
          title={`No successful backups yet for instance ${instance?.name ?? id}`}
        >
          Once a backup lands here you'll be able to scrub through the
          history.
        </Alert>
      </div>
    );
  }

  const changed = diffQuery.data;
  const changeSummary = changed
    ? summariseDiff(changed)
    : null;

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 border-b border-border pb-3">
        <div className="min-w-0">
          <Link
            to="/backups"
            className="inline-flex items-center gap-1 text-sm text-muted-fg hover:text-accent"
          >
            <ArrowLeft className="h-4 w-4" /> back to backups
          </Link>
          <h1 className="mt-1 text-xl font-semibold">
            {instance?.name ?? `Instance ${id}`}
            <span className="ml-2 font-normal text-muted-fg">
              · history ({backups.length} backups)
            </span>
          </h1>
        </div>
        {focused && (
          <div className="flex shrink-0 gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => nav(`/backups/${focused.id}/view`)}
              title="Open the focused backup in a single-view tab"
            >
              Open
            </Button>
            {previous && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() =>
                  nav(`/backups/diff/${previous.id}/${focused.id}`)
                }
              >
                <Split className="h-4 w-4" />
                Side-by-side diff
              </Button>
            )}
          </div>
        )}
      </div>

      {/* Timeline */}
      <div className="flex flex-col gap-2 border-b border-border py-3">
        <div className="flex items-center justify-between gap-3 text-sm">
          <Button
            variant="secondary"
            size="sm"
            disabled={focusIdx <= 0}
            onClick={() => setFocusIdx(Math.max(0, focusIdx - 1))}
            aria-label="Previous backup"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <div className="flex-1">
            <input
              type="range"
              min={0}
              max={Math.max(0, backups.length - 1)}
              step={1}
              value={focusIdx < 0 ? 0 : focusIdx}
              onChange={onSliderChange}
              aria-label="Backup timeline"
              aria-valuetext={
                focused
                  ? new Date(focused.started_at).toLocaleString()
                  : undefined
              }
              className="w-full"
            />
            <div className="mt-1 flex justify-between text-xs text-muted-fg">
              <span title={backups[0]?.started_at}>
                {new Date(backups[0].started_at).toLocaleDateString()}
              </span>
              {/* Position counter is the primary feedback for keyboard /
                  screen-reader users scrubbing the timeline — wrap in a
                  polite live region so assistive tech announces the new
                  position without interrupting ongoing speech. */}
              <span
                className="font-mono"
                aria-live="polite"
                aria-atomic="true"
              >
                #{focusIdx + 1} / {backups.length}
              </span>
              <span title={backups[backups.length - 1]?.started_at}>
                {new Date(
                  backups[backups.length - 1].started_at,
                ).toLocaleDateString()}
              </span>
            </div>
          </div>
          <Button
            variant="secondary"
            size="sm"
            disabled={focusIdx >= backups.length - 1}
            onClick={() =>
              setFocusIdx(Math.min(backups.length - 1, focusIdx + 1))
            }
            aria-label="Next backup"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>

        {/* Focus summary + change summary vs previous. */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {focused && (
            <>
              <span className="text-muted-fg">Focused:</span>
              <span className="font-mono">
                {new Date(focused.started_at).toLocaleString()}
              </span>
              {focused.tag && <Badge tone="muted">{focused.tag}</Badge>}
              <span className="text-muted-fg">·</span>
              <span className="font-mono text-muted-fg">
                {Math.round(focused.size_bytes / 1024)} KB
              </span>
            </>
          )}
          {changeSummary && previous && (
            <>
              <span className="mx-2 text-muted-fg">vs previous:</span>
              {changeSummary.added > 0 && (
                <Badge tone="success">+{changeSummary.added}</Badge>
              )}
              {changeSummary.removed > 0 && (
                <Badge tone="danger">−{changeSummary.removed}</Badge>
              )}
              {changeSummary.modified > 0 && (
                <Badge tone="warn">
                  ~{changeSummary.modified} modified
                </Badge>
              )}
              {changeSummary.added +
                changeSummary.removed +
                changeSummary.modified ===
                0 && (
                <span className="text-muted-fg">no semantic changes</span>
              )}
            </>
          )}
          {!previous && focused && (
            <>
              <span className="mx-2 text-muted-fg">·</span>
              <span className="text-muted-fg">
                first successful backup — nothing to diff against
              </span>
            </>
          )}
        </div>
      </div>

      {/* Focused backup's Structured view */}
      <div className="flex-1 overflow-hidden">
        {focused && (
          <Suspense
            fallback={
              <div className="p-6 text-sm text-muted-fg">Loading view…</div>
            }
          >
            <ParsedBackupView backupId={focused.id} />
          </Suspense>
        )}
      </div>

      {/* Floating hint: tell the operator the 'h' shortcut exists
          whenever we have a focused anchor and the drawer isn't
          open. Low-key pill in the bottom-left. */}
      {focusedAnchor && blameAnchor === null && (
        <button
          type="button"
          onClick={() => setBlameAnchor(focusedAnchor)}
          className="fixed bottom-4 left-4 z-30 inline-flex items-center gap-1.5 rounded-full border border-border bg-bg/95 px-3 py-1.5 text-xs font-medium text-muted-fg shadow-lg backdrop-blur transition-colors hover:bg-muted/60 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
          title={`Blame: ${focusedAnchor}`}
        >
          <Clock aria-hidden="true" className="h-3.5 w-3.5" />
          <span>History of this field</span>
          <kbd className="ml-1 rounded border border-border bg-muted px-1 text-[10px]">
            h
          </kbd>
        </button>
      )}

      {/* Blame drawer — mounted here so it slides in over the
          Structured view. Closed state renders nothing. */}
      <AnchorHistoryDrawer
        instanceId={id}
        anchor={blameAnchor}
        onClose={() => setBlameAnchor(null)}
      />
    </div>
  );
}

/** Summary badges for the "vs previous" strip. Totals across every
 *  section so the number rolls up at-a-glance; the inline DOM
 *  highlighting still gives per-row detail. */
function summariseDiff(
  diff: import("@/api/parsedTypes").ConfigDiff,
): { added: number; removed: number; modified: number } {
  let added = 0;
  let removed = 0;
  let modified = 0;
  for (const v of Object.values(diff as unknown as Record<string, unknown>)) {
    if (!v || typeof v !== "object") continue;
    const sd = v as {
      added?: unknown[];
      removed?: unknown[];
      modified?: unknown[];
    };
    added += sd.added?.length ?? 0;
    removed += sd.removed?.length ?? 0;
    modified += sd.modified?.length ?? 0;
  }
  return { added, removed, modified };
}
