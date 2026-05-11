import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ChevronLeft, ChevronRight, Clock, Split } from "lucide-react";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Tabs } from "@/components/ui/Tabs";
import {
  useAnchorBlameSummary,
  useBackups,
  useInstances,
  useParsedDiffPair,
} from "@/api/queries";
import { collectChangedAnchors } from "@/lib/changedAnchors";
import { formatLocal, formatLocalDate } from "@/lib/datetime";
import { useFocusedAnchor } from "@/lib/useFocusedAnchor";
import { useBlameHotkey } from "@/lib/useBlameHotkey";
import { AnchorHistoryDrawer } from "@/components/xref/AnchorHistoryDrawer";
import { AnchorBlameProvider } from "@/components/xref/AnchorBlame";
import { RawXmlPanel } from "@/components/view/RawXmlPanel";
import { useToast } from "@/components/ui/Toast";

type HistoryViewTab = "structured" | "raw";

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
  const toast = useToast();

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

  // v0.40.0: blame summary keyed on the focused backup — tooltip
  // shows "as of this backup" rather than "as of now" so scrubbing
  // through history gives truthful rollback info.
  const blameSummary = useAnchorBlameSummary(id, focused?.id);
  const blameAnchors = blameSummary.data?.anchors;
  const blameIndexed = blameSummary.data?.indexed ?? false;
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
      // v0.41.0: exempt the Tabs widget (Structured / Raw toggle).
      // It uses the same ArrowLeft / ArrowRight keys internally and
      // without this guard both the tab switch AND the timeline
      // scrubber would advance on a single key press when a tab has
      // focus.
      if (target?.closest('[role="tablist"], [role="tab"]')) return;
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

  // Blame drawer (v0.24.0): ``h`` opens the AnchorHistoryDrawer for
  // the nearest visible row / field; ``Esc`` closes it (inside the
  // drawer). Shared with ``BackupView`` via ``useBlameHotkey``.
  const focusedAnchor = useFocusedAnchor(true);
  const onNoAnchorToast = useCallback(() => {
    toast.info("Scroll to a field and press h again");
  }, [toast]);
  const { blameAnchor, openBlame, closeBlame } = useBlameHotkey({
    enabled: true,
    focusedAnchor,
    onNoAnchor: onNoAnchorToast,
  });

  // Structured / Raw XML toggle for the focused backup panel —
  // mirrors BackupView so operators can inspect the XML without
  // leaving the scrubbable history view.
  const [viewTab, setViewTab] = useState<HistoryViewTab>("structured");

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
          {/* v0.41.18: previously pointed to ``/backups`` with a
              "Back to backups" label, but the natural entry into
              this page is ``/instances/:id`` → "Scrub through
              history", so the back link now returns the operator
              to that instance's detail page. */}
          <Link
            to={`/instances/${id}`}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/40 px-2 py-1 text-sm font-medium text-fg transition-colors hover:border-accent hover:bg-accent/10 hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
          >
            <ArrowLeft className="h-4 w-4 text-accent" /> Back to{" "}
            {instance?.name ?? `instance ${id}`}
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
              onClick={() => nav(`/instances/${id}/changes`)}
              title="Every row that has changed since the first backup"
            >
              Changes
            </Button>
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
                  nav(
                    `/backups/diff/${previous.id}/${focused.id}?from=${focused.id}`,
                  )
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
                  ? formatLocal(focused.started_at)
                  : undefined
              }
              className="w-full"
            />
            <div className="mt-1 flex justify-between text-xs text-muted-fg">
              <span title={backups[0]?.started_at}>
                {formatLocalDate(backups[0].started_at)}
              </span>
              {/* Visual position counter. The slider's own
                  ``aria-valuetext`` already drives the screen-reader
                  announcement for this view (with the localised
                  timestamp), throttled properly by the AT. Adding
                  ``aria-live="polite"`` here would queue a second
                  announcement per drag tick — which screen readers
                  drain for seconds after the drag ends. So this is
                  visual-only. */}
              <span className="font-mono">
                #{focusIdx + 1} / {backups.length}
              </span>
              <span title={backups[backups.length - 1]?.started_at}>
                {formatLocalDate(backups[backups.length - 1].started_at)}
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
                {formatLocal(focused.started_at)}
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
          {/* v0.37.0 — "+N since first backup" precomputed summary.
              Clicking the cluster opens the full structural diff
              against the oldest-still-on-disk backup. Rendered only
              when (a) the focused row isn't itself the first (its
              changes_since_first would be all zeros) and (b) the
              backend has a cached summary to show. */}
          {focused?.changes_since_first && focusIdx > 0 && (
            <>
              <span className="mx-2 text-muted-fg">·</span>
              <button
                type="button"
                onClick={() => {
                  // ``backups`` is sorted ASC, so ``backups[0]`` is
                  // the oldest-still-on-disk — exactly the base the
                  // backend used for changes_since_first.
                  const first = backups[0];
                  if (first && first.id !== focused.id) {
                    nav(
                      `/backups/diff/${first.id}/${focused.id}?from=${focused.id}`,
                    );
                  }
                }}
                className="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg/50 px-2 py-0.5 text-xs text-muted-fg transition-colors hover:bg-muted/60 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
                title={
                  backups[0]
                    ? `Open full diff vs ${formatLocal(backups[0].started_at)}`
                    : "Open full diff vs first backup"
                }
              >
                <span>since first:</span>
                {focused.changes_since_first.added > 0 && (
                  <Badge tone="success">
                    +{focused.changes_since_first.added}
                  </Badge>
                )}
                {focused.changes_since_first.removed > 0 && (
                  <Badge tone="danger">
                    −{focused.changes_since_first.removed}
                  </Badge>
                )}
                {focused.changes_since_first.modified > 0 && (
                  <Badge tone="warn">
                    ~{focused.changes_since_first.modified}
                  </Badge>
                )}
                {focused.changes_since_first.added +
                  focused.changes_since_first.removed +
                  focused.changes_since_first.modified ===
                  0 && <span>no semantic changes</span>}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Focused backup's panel — Structured (default) or Raw XML.
          Tab state is client-side; operators toggle per session.
          AnchorBlameProvider wraps both so Monaco's hover provider
          reads the same summary the Structured tooltip uses. */}
      {focused && (
        <>
          <Tabs
            className="mt-2"
            value={viewTab}
            onChange={(next) => setViewTab(next as HistoryViewTab)}
            ariaLabel="Focused backup view"
            idPrefix="history-view"
            items={[
              { id: "structured", label: "Structured" },
              { id: "raw", label: "Raw XML" },
            ]}
          />
          <div className="flex-1 overflow-hidden rounded-b border border-t-0 border-border">
            <Suspense
              fallback={
                <div className="p-6 text-sm text-muted-fg">Loading view…</div>
              }
            >
              <AnchorBlameProvider
                anchors={blameAnchors}
                indexed={blameIndexed}
                openBlame={openBlame}
              >
                {viewTab === "structured" ? (
                  <ParsedBackupView backupId={focused.id} />
                ) : (
                  <RawXmlPanel backupId={focused.id} />
                )}
              </AnchorBlameProvider>
            </Suspense>
          </div>
        </>
      )}

      {/* Floating hint: tell the operator the 'h' shortcut exists
          whenever we have a focused anchor and the drawer isn't
          open. Low-key pill in the bottom-left. */}
      {focusedAnchor && blameAnchor === null && (
        <button
          type="button"
          onClick={() => openBlame(focusedAnchor)}
          className="fixed bottom-4 left-4 z-30 inline-flex items-center gap-1.5 rounded-full border border-border bg-bg px-3 py-1.5 text-xs font-medium text-muted-fg shadow-lg transition-colors hover:bg-muted/60 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
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
          Structured view. Closed state renders nothing. The
          ``currentBackupId`` lets the drawer's "open this backup"
          links carry ``?from=…`` so the destination page shows a
          Return-to-backup pill. */}
      <AnchorHistoryDrawer
        instanceId={id}
        anchor={blameAnchor}
        currentBackupId={focused?.id}
        onClose={closeBlame}
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
