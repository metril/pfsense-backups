import { useEffect, useMemo, useRef } from "react";
import { Link } from "react-router-dom";
import { Clock, ExternalLink, X } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import {
  useAnchorHistory,
  type AnchorHistoryChange,
} from "@/api/queries";
import { anchorHumanLabel } from "@/lib/anchorLabel";

/**
 * Per-anchor blame drawer. Opens when the operator hits ``h`` on a
 * focused row / field in the Structured view (or when the caller
 * explicitly sets ``anchor``) and lists every successful backup of
 * the enclosing instance with the anchor's value at that point in
 * time. Change rows get the warn accent; unchanged runs collapse
 * into "× runs with no change" summaries so the list stays scan-
 * able on instances with hundreds of backups.
 *
 * The drawer is a controlled component — parent owns ``anchor`` +
 * ``onClose`` state. Closed (``anchor === null``) renders nothing
 * so we don't pay for the fetch when the drawer isn't in use.
 *
 * Accessibility:
 *   - ``role="dialog"`` + ``aria-modal="true"`` so screen readers
 *     treat the content outside the drawer as inert.
 *   - ``Tab`` / ``Shift+Tab`` cycle within the drawer (simple focus
 *     trap — the dialog only holds a handful of focusable elements).
 *   - Focus lands on the close button on open and restores to the
 *     element that held focus before the drawer mounted when it
 *     closes (parent-triggered or Esc / tap-outside).
 *   - A full-viewport backdrop behind the drawer captures clicks
 *     anywhere outside the panel; mobile users can dismiss without
 *     having to hit the tiny close button.
 */
export function AnchorHistoryDrawer({
  instanceId,
  anchor,
  label,
  currentBackupId,
  onClose,
}: {
  instanceId: number;
  anchor: string | null;
  /** Short human label for the header (``"alias: RFC1918"`` etc.).
   *  Optional override — when omitted, the drawer derives one from
   *  the anchor id + the first change's value via
   *  ``anchorHumanLabel`` so the header never falls back to the raw
   *  ``xref-rule-tracker_…`` id. */
  label?: string;
  /** The backup the drawer was opened from. When set, each
   *  timeline-row's "open this backup" link carries ``?from={id}``
   *  so the destination page can render a "Return to backup #N"
   *  pill. */
  currentBackupId?: number;
  onClose: () => void;
}) {
  const query = useAnchorHistory(instanceId, anchor);
  // Derive the human header label from the first "is_change" entry
  // of the full history — that carries the row value dict
  // (``descr`` / ``name`` / ``refid``) that the label helper uses.
  // While the history is loading the header falls back to ``section
  // · tail`` (still readable), then upgrades in-place once the row
  // value is available.
  const firstChange = query.data?.entries.find((e) => e.is_change);
  const valueForLabel = firstChange?.value;
  const derivedLabel = anchor ? anchorHumanLabel(anchor, valueForLabel) : "";
  const headerLabel = label ?? derivedLabel;

  const dialogRef = useRef<HTMLDivElement | null>(null);
  const closeBtnRef = useRef<HTMLButtonElement | null>(null);
  // Remember who had focus before the drawer opened so we can
  // restore on close. ``HTMLElement`` only — if the pre-open focus
  // was ``<body>`` we don't attempt restore.
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!anchor) return;
    const prev = document.activeElement;
    restoreFocusRef.current =
      prev instanceof HTMLElement && prev !== document.body ? prev : null;
    // Defer focus to the next frame — the dialog may not be mounted
    // in the DOM yet when the effect runs under Suspense.
    const id = window.setTimeout(() => closeBtnRef.current?.focus(), 0);
    return () => {
      window.clearTimeout(id);
      const target = restoreFocusRef.current;
      // Only restore if the element is still in the DOM.
      if (target && document.body.contains(target)) {
        target.focus();
      }
    };
  }, [anchor]);

  useEffect(() => {
    if (!anchor) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === "Tab") {
        // Focus trap: keep Tab inside the dialog.
        const root = dialogRef.current;
        if (!root) return;
        const focusables = root.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement;
        if (e.shiftKey && active === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [anchor, onClose]);

  // Collapse consecutive "no change" runs into summary pills so the
  // drawer doesn't become a wall of identical rows on instances with
  // weekly backups across a year.
  const rendered = useMemo(() => collapse(query.data?.entries ?? []), [query.data]);

  if (!anchor) return null;

  return (
    <>
      {/* Backdrop — click / tap anywhere outside the panel to close.
          ``aria-hidden`` so the dialog's content remains the only a11y
          target. ``z-[45]`` sits ABOVE the floating back-pill
          (``z-40``) so the pill doesn't intercept clicks while the
          drawer is open, and BELOW the drawer panel (``z-50``) so the
          dialog itself stays interactive. */}
      <div
        aria-hidden="true"
        onClick={onClose}
        className="fixed inset-0 z-[45] bg-black/20"
      />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="Anchor history"
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-border bg-bg shadow-2xl"
      >
        <div className="flex items-start justify-between gap-3 border-b border-border p-3">
          <div className="min-w-0">
            <div className="flex items-center gap-1 text-xs text-muted-fg">
              <Clock className="h-3 w-3" />
              <span>Blame timeline</span>
            </div>
            <h2 className="mt-1 truncate text-sm font-semibold">
              {headerLabel || anchor}
            </h2>
            <p
              className="mt-0.5 truncate font-mono text-[10px] text-muted-fg"
              title={anchor ?? undefined}
            >
              {anchor}
            </p>
          </div>
          <Button
            ref={closeBtnRef}
            variant="secondary"
            size="sm"
            onClick={onClose}
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto p-3 text-sm">
          {query.isLoading && (
            <div className="text-muted-fg">Walking every backup…</div>
          )}
          {query.isError && (
            <div className="text-danger">{String(query.error)}</div>
          )}
          {query.data && rendered.length === 0 && (
            <div className="text-muted-fg">
              No successful backups to compare.
            </div>
          )}
          <ol className="space-y-2">
            {rendered.map((r) =>
              r.kind === "run" ? (
                <li
                  key={`run-${r.startIdx}`}
                  className="flex items-center gap-2 text-xs text-muted-fg"
                >
                  <span className="h-px flex-1 bg-border" />
                  {r.count} run{r.count === 1 ? "" : "s"} with no change
                  <span className="h-px flex-1 bg-border" />
                </li>
              ) : (
                <EntryRow
                  key={r.entry.backup_id}
                  entry={r.entry}
                  anchor={anchor}
                  currentBackupId={currentBackupId}
                />
              ),
            )}
          </ol>
        </div>
      </div>
    </>
  );
}

// ---------------------- internals ---------------------------------

function EntryRow({
  entry,
  anchor,
  currentBackupId,
}: {
  entry: AnchorHistoryChange;
  anchor: string | null;
  currentBackupId?: number;
}) {
  const when = new Date(entry.started_at);
  // Build the target URL with the anchor (so BackupView can scroll
  // to it) and, when we know where we came from, the ``from`` param
  // that drives the ``ReturnToBackupPill`` on the destination.
  const params = new URLSearchParams();
  if (anchor) params.set("anchor", anchor);
  if (currentBackupId !== undefined && currentBackupId !== entry.backup_id) {
    params.set("from", String(currentBackupId));
  }
  const qs = params.toString();
  const href = `/backups/${entry.backup_id}/view${qs ? `?${qs}` : ""}`;
  return (
    <li
      className={
        entry.is_change
          ? "rounded border border-[hsl(var(--warn)/0.4)] bg-[hsl(var(--warn)/0.06)] p-2"
          : "rounded border border-transparent p-2"
      }
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs">
          <span className="font-mono">{when.toLocaleString()}</span>
          {entry.is_change && <Badge tone="warn">changed</Badge>}
          {entry.value === null && <Badge tone="muted">missing</Badge>}
        </div>
        {/* ``Link`` handles SPA navigation on plain click and lets
            the browser handle middle-click / Cmd+click to open in a
            new tab. An ``onClick`` with ``preventDefault`` would
            kill both behaviours. */}
        <Link
          to={href}
          className="inline-flex items-center gap-1 text-xs text-muted-fg hover:text-accent"
          title="Open this backup and scroll to the changed row"
        >
          <ExternalLink className="h-3 w-3" />
          #{entry.backup_id}
        </Link>
      </div>
      <div className="mt-1.5 whitespace-pre-wrap break-words font-mono text-[11px] text-muted-fg">
        {formatValue(entry.value)}
      </div>
    </li>
  );
}

function formatValue(value: AnchorHistoryChange["value"]): string {
  if (value === null) return "—";
  if (typeof value === "string") return value;
  // Row-shaped object: pretty-print to two levels so the drawer stays
  // readable without scrolling horizontally.
  return JSON.stringify(value, null, 2);
}

type Rendered =
  | { kind: "entry"; entry: AnchorHistoryChange }
  | { kind: "run"; count: number; startIdx: number };

/** Collapse consecutive ``is_change === false`` rows into a single
 *  "N runs with no change" summary so operators aren't scrolling
 *  through dozens of identical entries between two actual changes.
 *  Always leaves the first entry visible (the baseline) and the
 *  change entries themselves. */
function collapse(entries: AnchorHistoryChange[]): Rendered[] {
  const out: Rendered[] = [];
  let runCount = 0;
  let runStart = -1;
  for (let i = 0; i < entries.length; i++) {
    const e = entries[i];
    const isBaseline = i === 0;
    if (!e.is_change && !isBaseline) {
      if (runCount === 0) runStart = i;
      runCount += 1;
      continue;
    }
    if (runCount > 0) {
      out.push({ kind: "run", count: runCount, startIdx: runStart });
      runCount = 0;
    }
    out.push({ kind: "entry", entry: e });
  }
  if (runCount > 0) {
    out.push({ kind: "run", count: runCount, startIdx: runStart });
  }
  return out;
}
