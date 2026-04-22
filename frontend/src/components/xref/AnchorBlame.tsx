/**
 * Inline blame affordance for the Structured + Raw XML views.
 *
 * - ``AnchorBlameProvider`` — page-level context that carries the
 *   per-anchor "latest event" map (fetched once via
 *   ``useAnchorBlameSummary``) plus an optional ``openBlame``
 *   callback. Rendered by ``BackupView`` and ``InstanceHistory`` at
 *   the top of the viewer tree so every anchored row inside the
 *   parsed view can opt into the tooltip + click-to-open drawer.
 *
 * - ``AnchorBlameTooltip`` — wrap any anchored element
 *   (``<dt id="field-…">``, ``<tr id="xref-…">``, etc.). Renders a
 *   Radix tooltip with a warn-accented card, human-readable label,
 *   relative-time stamp, and a clickable "View full history" CTA
 *   that invokes ``openBlame`` from context. When the anchor has no
 *   events (never changed / instance not indexed), the wrapper is a
 *   no-op — renders children unwrapped so the DOM is identical.
 *
 * - ``BlameDot`` — persistent, always-visible click affordance for
 *   anchored rows whose blame data is available. Tiny warn-tinted
 *   dot; opacity 40% at rest, 100% on hover. Acts as the
 *   "discoverable" entry point into blame (the tooltip only appears
 *   on hover; the dot is visible at a glance).
 */

import * as RadixTooltip from "@radix-ui/react-tooltip";
import {
  createContext,
  useContext,
  useMemo,
  useRef,
  type ReactNode,
} from "react";
import { Clock } from "lucide-react";
import type { AnchorBlameSummaryEntry } from "@/api/queries";
import { formatRelative } from "@/lib/formatRelative";
import { anchorHumanLabel, parseAnchorId, sectionLabel } from "@/lib/anchorLabel";
import { cn } from "@/lib/cn";

interface BlameContextValue {
  /** Indexed on the anchor's ``xref-`` / ``field-`` id. ``undefined``
   *  when the anchor has no events (never changed). */
  anchors: Record<string, AnchorBlameSummaryEntry>;
  /** False when the instance predates v0.40.0 indexing. Tooltip
   *  consumers use it to suppress hover behaviour entirely so users
   *  don't see "no blame" hints that actually just mean "not yet
   *  reindexed." */
  indexed: boolean;
  /** Open the blame drawer for a given anchor. Null when no drawer
   *  is wired (e.g. in a read-only context). Populated by pages that
   *  render ``<AnchorHistoryDrawer>``. */
  openBlame?: (anchorId: string) => void;
}

const BlameContext = createContext<BlameContextValue | null>(null);

export function AnchorBlameProvider({
  anchors,
  indexed,
  openBlame,
  children,
}: {
  anchors: Record<string, AnchorBlameSummaryEntry> | undefined;
  indexed: boolean;
  openBlame?: (anchorId: string) => void;
  children: ReactNode;
}) {
  // Reference-identity guard: TanStack background refetches hand us
  // a fresh ``anchors`` object even when the payload hasn't changed
  // in any meaningful way. Re-creating the context value on every
  // refetch would force every ``AnchorBlameTooltip`` (hundreds in a
  // large Structured view) to re-render unnecessarily. We snapshot
  // the incoming anchors and compare a compact signature
  // (entry count + a hash of sorted keys) — if nothing changed,
  // reuse the previous reference.
  const prevRef = useRef<{
    signature: string;
    anchors: Record<string, AnchorBlameSummaryEntry>;
  } | null>(null);
  const stableAnchors = useMemo(() => {
    const next = anchors ?? {};
    const keys = Object.keys(next).sort();
    let sum = 0;
    for (const k of keys) sum += next[k]?.backup_id ?? 0;
    const signature = `${keys.length}:${keys[0] ?? ""}:${keys[keys.length - 1] ?? ""}:${sum}`;
    const prev = prevRef.current;
    if (prev && prev.signature === signature) {
      return prev.anchors;
    }
    prevRef.current = { signature, anchors: next };
    return next;
  }, [anchors]);

  const value = useMemo<BlameContextValue>(
    () => ({ anchors: stableAnchors, indexed, openBlame }),
    [stableAnchors, indexed, openBlame],
  );
  return (
    <BlameContext.Provider value={value}>{children}</BlameContext.Provider>
  );
}

export function useAnchorBlame(): BlameContextValue | null {
  return useContext(BlameContext);
}

/** Lookup helper used by the Monaco hover provider and anywhere
 *  else that needs the raw summary entry for an anchor id. Returns
 *  ``null`` when: (a) no provider is mounted, (b) instance isn't
 *  indexed, or (c) the anchor has no events. */
export function useBlameForAnchor(
  anchorId: string | null | undefined,
): AnchorBlameSummaryEntry | null {
  const ctx = useAnchorBlame();
  if (ctx == null || !ctx.indexed || !anchorId) return null;
  return ctx.anchors[anchorId] ?? null;
}

function kindLabel(kind: AnchorBlameSummaryEntry["kind"]): string {
  switch (kind) {
    case "added":
      return "added";
    case "modified":
      return "modified";
    case "removed":
      return "removed";
    case "reordered":
      return "reordered";
  }
}

/** Build the tooltip body for a blame entry. Exposed so the Monaco
 *  hover provider can reuse the same phrasing in a markdown string. */
export function blameTooltipText(entry: AnchorBlameSummaryEntry): string {
  const rel = formatRelative(entry.occurred_at);
  const abs = new Date(entry.occurred_at).toLocaleString();
  return `Last ${kindLabel(entry.kind)} ${rel} (backup #${entry.backup_id}, ${abs}) · press h for full history`;
}

/** Wraps children with a Radix tooltip that shows blame info when
 *  an entry is available. The tree shape is intentionally stable —
 *  we ALWAYS render the ``RadixTooltip.Root`` + ``Trigger asChild``
 *  so the wrapped DOM element (``<tr>`` / ``<dt>``) keeps the same
 *  identity across blame loads. If we toggled the whole wrapper on
 *  entry presence, React would unmount + remount the child on every
 *  refetch, destroying any DOM state (focus, selection) on that row.
 *
 *  The ``Portal`` / ``Content`` only render when we have blame data,
 *  so the cost when blame isn't available is just a context provider
 *  and a pair of empty listener-bearing trigger props.
 *
 *  Visuals: warn-tinted left stripe + clock glyph + "Blame · {section}"
 *  header, human-readable label, relative-time, and a clickable
 *  "View full history →" CTA. Styled distinctively from the generic
 *  app tooltip so operators can tell blame content apart at a
 *  glance. */
export function AnchorBlameTooltip({
  anchorId,
  children,
}: {
  anchorId: string | null | undefined;
  children: ReactNode;
}) {
  const entry = useBlameForAnchor(anchorId);
  const ctx = useAnchorBlame();
  const parsed = anchorId ? parseAnchorId(anchorId) : null;
  const scope = parsed?.scope ?? "";
  // The summary endpoint doesn't carry the per-anchor ``value`` dict
  // (that'd inflate the payload for hundreds of anchors we may never
  // inspect). Human label falls back to ``section · tail``; the full
  // drawer fetches the history and can show a richer label if needed.
  const humanLabel = anchorId ? anchorHumanLabel(anchorId, null) : "";
  const canOpen = entry != null && ctx?.openBlame != null && anchorId != null;

  return (
    <RadixTooltip.Root>
      <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
      {entry != null && (
        <RadixTooltip.Portal>
          <RadixTooltip.Content
            side="top"
            align="center"
            sideOffset={6}
            className={cn(
              "z-50 max-w-sm rounded-md border border-border border-l-2 border-l-warn",
              "bg-bg/95 px-3 py-2 text-sm text-fg shadow-xl backdrop-blur-sm",
              "data-[state=delayed-open]:animate-in data-[state=delayed-open]:fade-in-0",
            )}
          >
            <div className="flex items-start gap-2">
              <Clock
                aria-hidden
                className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warn"
              />
              <div className="min-w-0">
                <div className="text-[10px] font-semibold uppercase tracking-wide text-warn">
                  Blame · {sectionLabel(scope)}
                </div>
                <div className="mt-0.5 truncate font-medium text-fg">
                  {humanLabel}
                </div>
                <div className="mt-1 text-xs text-muted-fg">
                  Last {kindLabel(entry.kind)} {formatRelative(entry.occurred_at)} · backup #
                  {entry.backup_id}
                </div>
                {canOpen && (
                  <button
                    type="button"
                    onClick={() => ctx!.openBlame!(anchorId!)}
                    className={cn(
                      "mt-2 inline-flex items-center gap-1 rounded",
                      "bg-warn/10 px-2 py-0.5 text-xs font-medium text-warn",
                      "hover:bg-warn/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-warn/40",
                    )}
                  >
                    View full history →
                  </button>
                )}
                <div className="mt-1 text-[10px] text-muted-fg">
                  or press{" "}
                  <kbd className="rounded border border-border bg-muted/40 px-1 text-[10px]">
                    h
                  </kbd>
                </div>
              </div>
            </div>
            <RadixTooltip.Arrow className="fill-warn" />
          </RadixTooltip.Content>
        </RadixTooltip.Portal>
      )}
    </RadixTooltip.Root>
  );
}

/** Persistent dot indicating the row has blame data and offering a
 *  click path to the drawer. Renders nothing when there's no blame
 *  entry for this anchor OR no ``openBlame`` callback in context.
 *  Tiny on purpose — discoverable without dominating. */
export function BlameDot({
  anchorId,
  className,
}: {
  anchorId: string | null | undefined;
  className?: string;
}) {
  const entry = useBlameForAnchor(anchorId);
  const ctx = useAnchorBlame();
  if (!entry || !ctx?.openBlame || !anchorId) return null;
  return (
    <button
      type="button"
      aria-label="Open blame history for this row"
      title="Open blame history (or press h)"
      onClick={(e) => {
        e.stopPropagation();
        ctx.openBlame?.(anchorId);
      }}
      className={cn(
        "inline-block h-1.5 w-1.5 rounded-full bg-warn/60 opacity-40",
        "transition-opacity hover:opacity-100 focus-visible:opacity-100",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-warn/40",
        className,
      )}
    />
  );
}
