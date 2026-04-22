/**
 * Inline blame affordance for the Structured + Raw XML views.
 *
 * - ``AnchorBlameProvider`` — page-level context that carries the
 *   per-anchor "latest event" map (fetched once via
 *   ``useAnchorBlameSummary``). Rendered by ``BackupView`` and
 *   ``InstanceHistory`` at the top of the viewer tree so every
 *   anchored row inside the parsed view can opt into the tooltip
 *   without a prop drill.
 *
 * - ``AnchorBlameTooltip`` — wrap any anchored element
 *   (``<dt id="field-…">``, ``<tr id="xref-…">``, etc.) and it
 *   renders a Radix tooltip showing "Last modified 3 days ago ·
 *   backup #42 · press h for full history." When the anchor has no
 *   events (never changed / instance not indexed), the wrapper is a
 *   no-op — renders children unwrapped so the DOM is identical to
 *   pre-v0.40.0.
 */

import * as RadixTooltip from "@radix-ui/react-tooltip";
import {
  createContext,
  useContext,
  useMemo,
  useRef,
  type ReactNode,
} from "react";
import type { AnchorBlameSummaryEntry } from "@/api/queries";
import { formatRelative } from "@/lib/formatRelative";

interface BlameContextValue {
  /** Indexed on the anchor's ``xref-`` / ``field-`` id. ``undefined``
   *  when the anchor has no events (never changed). */
  anchors: Record<string, AnchorBlameSummaryEntry>;
  /** False when the instance predates v0.40.0 indexing. Tooltip
   *  consumers use it to suppress hover behaviour entirely so users
   *  don't see "no blame" hints that actually just mean "not yet
   *  reindexed." */
  indexed: boolean;
}

const BlameContext = createContext<BlameContextValue | null>(null);

export function AnchorBlameProvider({
  anchors,
  indexed,
  children,
}: {
  anchors: Record<string, AnchorBlameSummaryEntry> | undefined;
  indexed: boolean;
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
    // Signature: `<count>:<first>:<last>:<backupIdSum>` — cheap to
    // compute, collision-safe enough for cache-invalidation
    // purposes (worst case is a missed re-render, not a bug).
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
    () => ({ anchors: stableAnchors, indexed }),
    [stableAnchors, indexed],
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
 *  and a pair of empty listener-bearing trigger props. */
export function AnchorBlameTooltip({
  anchorId,
  children,
}: {
  anchorId: string | null | undefined;
  children: ReactNode;
}) {
  const entry = useBlameForAnchor(anchorId);
  return (
    <RadixTooltip.Root>
      <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
      {entry != null && (
        <RadixTooltip.Portal>
          <RadixTooltip.Content
            side="top"
            align="center"
            sideOffset={4}
            className="z-50 max-w-xs rounded border border-border bg-bg px-2 py-1 text-xs text-fg shadow-lg data-[state=delayed-open]:animate-in data-[state=delayed-open]:fade-in-0"
          >
            {blameTooltipText(entry)}
            <RadixTooltip.Arrow className="fill-border" />
          </RadixTooltip.Content>
        </RadixTooltip.Portal>
      )}
    </RadixTooltip.Root>
  );
}
