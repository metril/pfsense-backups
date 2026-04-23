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
 * - ``BlameHoverTooltip`` — wraps an anchored row (``<dt>`` /
 *   ``<tr>``) and shows a **cursor-following** tooltip when the
 *   mouse is over any part of the row. Implemented by hand (not
 *   Radix Tooltip) because Radix positions its Content relative to
 *   the trigger's bounding rect — on a wide row that puts the
 *   tooltip at the row's midpoint, far from the cursor. v0.41.6
 *   renders the tooltip in a portal pinned to ``clientX/clientY``
 *   so it tracks the mouse. Keyboard focus falls back to anchoring
 *   the tooltip at the focused element's top-right corner.
 *
 * - ``BlameDot`` — persistent, always-visible click affordance for
 *   anchored rows whose blame data is available. No tooltip of its
 *   own any more (``BlameHoverTooltip`` covers the whole row), just
 *   a click target that opens the drawer.
 */

import {
  Children,
  cloneElement,
  createContext,
  isValidElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type FocusEvent as ReactFocusEvent,
  type ReactElement,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
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
  // refetch would force every consumer (hundreds in a large
  // Structured view) to re-render. Snapshot + compact signature
  // (entry count + first/last key + sum of backup ids) — if
  // unchanged, reuse the previous reference.
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

// ---------------------------------------------------------------- //
// Cursor-following tooltip
// ---------------------------------------------------------------- //

const HOVER_DELAY_MS = 250;
const CURSOR_OFFSET_PX = 14;
// Conservative estimates used only for edge-flip calculations — the
// tooltip's real size is set by content + max-width (Tailwind
// ``max-w-sm`` = 24rem = 384px). When the real bounds go off-screen
// we flip to the opposite side of the cursor.
const TOOLTIP_MAX_W = 400;
const TOOLTIP_MAX_H = 160;

interface TooltipPos {
  x: number;
  y: number;
}

/** Compose multiple event handlers into one. Called left-to-right;
 *  if any caller preventsDefault, subsequent ones still run — we do
 *  NOT short-circuit because our handlers are observational. */
function composeHandlers<E>(
  ...handlers: (((e: E) => void) | undefined)[]
): ((e: E) => void) | undefined {
  const defined = handlers.filter(Boolean) as ((e: E) => void)[];
  if (defined.length === 0) return undefined;
  if (defined.length === 1) return defined[0];
  return (e: E) => {
    for (const h of defined) h(e);
  };
}

/** Clamp a target tooltip position into the viewport, flipping to
 *  the opposite side of the cursor if we'd otherwise go off-screen. */
function clampToViewport(
  cursorX: number,
  cursorY: number,
  viewportW: number,
  viewportH: number,
): TooltipPos {
  let x = cursorX + CURSOR_OFFSET_PX;
  let y = cursorY + CURSOR_OFFSET_PX;
  if (x + TOOLTIP_MAX_W > viewportW) {
    x = Math.max(CURSOR_OFFSET_PX, cursorX - CURSOR_OFFSET_PX - TOOLTIP_MAX_W);
  }
  if (y + TOOLTIP_MAX_H > viewportH) {
    y = Math.max(CURSOR_OFFSET_PX, cursorY - CURSOR_OFFSET_PX - TOOLTIP_MAX_H);
  }
  return { x, y };
}

/** Wraps a single anchored element (``<dt>`` / ``<tr>``) and shows
 *  a cursor-following tooltip whenever the operator hovers anywhere
 *  inside that element. No-op when there's no blame data for the
 *  anchor, so unchanged rows render with zero overhead.
 *
 *  The tooltip is rendered in a portal and uses ``pointer-events:
 *  none`` — the cursor passes through it, so moving the mouse into
 *  the tooltip region doesn't fire ``mouseleave`` on the trigger.
 *  A knock-on: the tooltip itself can't host interactive elements.
 *  That's fine because the CTAs (open drawer, press ``h``) live
 *  elsewhere: clicking the ``BlameDot`` opens the drawer, ``h``
 *  does too from a focused row. The tooltip's only job is to show
 *  info under the cursor.
 */
export function BlameHoverTooltip({
  anchorId,
  children,
}: {
  anchorId: string | null | undefined;
  children: ReactNode;
}) {
  const entry = useBlameForAnchor(anchorId);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<TooltipPos>({ x: 0, y: 0 });
  const enterTimerRef = useRef<number | null>(null);
  const leaveTimerRef = useRef<number | null>(null);
  const rafRef = useRef<number | null>(null);
  const pendingPosRef = useRef<{ x: number; y: number } | null>(null);
  // v0.41.9: ``openRef`` shadows ``open`` so the mouse handlers
  // below can read the current open state without closing over
  // ``open`` as a dep. Without this, ``onMouseEnter`` / ``onMouseMove``
  // would need ``[open]`` in their useCallback deps, which would
  // recreate them every time ``setOpen`` fires — which happens on
  // every cursor-follow position update. New handler identities →
  // cloneElement returns new props → every cloned child
  // re-renders. On a <dl> with hundreds of rows, that's hundreds
  // of re-renders per mousemove. Refs sidestep the whole thing.
  //
  // v0.41.10: the ref is kept in sync INLINE at every ``setOpen``
  // call site — we used to mirror it in a ``useEffect(…, [open])``
  // but effects run after paint, leaving a ~16ms gap where
  // ``openRef.current`` is stale. That caused ``onMouseEnter`` to
  // fall into the 250ms hover-delay branch on fast sibling
  // transitions right after the tooltip opened.
  const openRef = useRef(open);

  // Teardown on unmount — clear any pending timers / frames so the
  // state setters don't fire after the component is gone (React
  // would just warn in strict mode).
  useEffect(() => {
    return () => {
      if (enterTimerRef.current !== null) {
        window.clearTimeout(enterTimerRef.current);
        enterTimerRef.current = null;
      }
      if (leaveTimerRef.current !== null) {
        window.clearTimeout(leaveTimerRef.current);
        leaveTimerRef.current = null;
      }
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, []);

  const schedulePositionUpdate = useCallback(() => {
    if (rafRef.current !== null) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      const p = pendingPosRef.current;
      if (!p) return;
      setPos(
        clampToViewport(p.x, p.y, window.innerWidth, window.innerHeight),
      );
    });
  }, []);

  // All six handlers are useCallback'd with stable deps so the
  // ``cloneElement`` pass below returns identical prop identities
  // render-to-render. That lets React bail out of re-rendering the
  // cloned children (e.g. hundreds of <dt>s in a large Dl) as the
  // cursor moves. The handlers read the current open state via
  // ``openRef`` instead of closing over ``open``.
  const cancelLeave = useCallback(() => {
    if (leaveTimerRef.current !== null) {
      window.clearTimeout(leaveTimerRef.current);
      leaveTimerRef.current = null;
    }
  }, []);

  const onMouseEnter = useCallback(
    (e: ReactMouseEvent) => {
      // Moving from one handler-bearing sibling into another (e.g.
      // <dt> → <dd>) fires mouseleave on the first AND mouseenter
      // on the second. Cancel any pending close so the tooltip
      // doesn't flicker as the cursor crosses the boundary.
      cancelLeave();
      pendingPosRef.current = { x: e.clientX, y: e.clientY };
      if (openRef.current) {
        // Already open: just update position instead of delaying.
        setPos(
          clampToViewport(
            e.clientX,
            e.clientY,
            window.innerWidth,
            window.innerHeight,
          ),
        );
        return;
      }
      if (enterTimerRef.current !== null) {
        window.clearTimeout(enterTimerRef.current);
      }
      enterTimerRef.current = window.setTimeout(() => {
        enterTimerRef.current = null;
        const p = pendingPosRef.current;
        if (!p) return;
        setPos(
          clampToViewport(p.x, p.y, window.innerWidth, window.innerHeight),
        );
        openRef.current = true;
        setOpen(true);
      }, HOVER_DELAY_MS);
    },
    [cancelLeave],
  );

  const onMouseMove = useCallback(
    (e: ReactMouseEvent) => {
      pendingPosRef.current = { x: e.clientX, y: e.clientY };
      if (openRef.current) schedulePositionUpdate();
    },
    [schedulePositionUpdate],
  );

  const onMouseLeave = useCallback(() => {
    // Short grace period before closing — if the cursor is crossing
    // into a sibling of the same group (e.g. from <dt> to <dd>) the
    // sibling's ``onMouseEnter`` fires almost immediately and will
    // cancel this timer via ``cancelLeave()``. Without the grace,
    // the tooltip closes and re-opens with the hover delay, which
    // reads as a flicker.
    if (enterTimerRef.current !== null) {
      window.clearTimeout(enterTimerRef.current);
      enterTimerRef.current = null;
    }
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    cancelLeave();
    leaveTimerRef.current = window.setTimeout(() => {
      leaveTimerRef.current = null;
      pendingPosRef.current = null;
      openRef.current = false;
      setOpen(false);
    }, 50);
  }, [cancelLeave]);

  const onFocus = useCallback(
    (e: ReactFocusEvent) => {
      // Keyboard users don't have a cursor; anchor the tooltip to
      // the focused element's top-right corner so it still appears
      // near what they're reading. ``currentTarget`` is the cloned
      // child.
      cancelLeave();
      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
      setPos(
        clampToViewport(
          rect.right,
          rect.top,
          window.innerWidth,
          window.innerHeight,
        ),
      );
      openRef.current = true;
      setOpen(true);
    },
    [cancelLeave],
  );

  const onBlur = useCallback(() => {
    openRef.current = false;
    setOpen(false);
  }, []);

  // Children may be one element (a <tr>) or several (a <dt> + <dd>
  // pair in a Dl — its parent is a ``display: grid`` <dl> that
  // doesn't allow a wrapper <div>, so the tooltip needs to clone
  // each grid item individually and attach the same mouse handlers
  // to all of them). Mouse entering any of them opens the tooltip;
  // leaving the whole group closes it.
  //
  // Because ``onMouseEnter`` / ``onMouseLeave`` are non-bubbling
  // React synthetic events, moving between sibling handler-bearing
  // elements WOULD cause a close-then-reopen flicker. We coalesce
  // that with a ``leaveTimerRef`` debounce: ``mouseLeave`` on one
  // element schedules a close, and a ``mouseEnter`` on the next
  // sibling (or on the same element) cancels it.
  const childArr = Children.toArray(children);

  // No blame entry → render children untouched. Avoids every row
  // carrying dead event handlers.
  if (!entry || !anchorId) return <>{childArr}</>;

  type ChildProps = {
    onMouseEnter?: (e: ReactMouseEvent) => void;
    onMouseMove?: (e: ReactMouseEvent) => void;
    onMouseLeave?: (e: ReactMouseEvent) => void;
    onFocus?: (e: ReactFocusEvent) => void;
    onBlur?: (e: ReactFocusEvent) => void;
  };

  // Clone each valid element child, adding the shared handler set.
  // Non-element children (strings, fragments, null) pass through
  // unchanged.
  const clonedChildren = childArr.map((child, idx) => {
    if (!isValidElement(child)) return child;
    const el = child as ReactElement<ChildProps>;
    const cp = (el.props ?? {}) as ChildProps;
    return cloneElement(el, {
      key: el.key ?? `blame-child-${idx}`,
      onMouseEnter: composeHandlers<ReactMouseEvent>(cp.onMouseEnter, onMouseEnter),
      onMouseMove: composeHandlers<ReactMouseEvent>(cp.onMouseMove, onMouseMove),
      onMouseLeave: composeHandlers<ReactMouseEvent>(cp.onMouseLeave, onMouseLeave),
      onFocus: composeHandlers<ReactFocusEvent>(cp.onFocus, onFocus),
      onBlur: composeHandlers<ReactFocusEvent>(cp.onBlur, onBlur),
    } as Partial<ChildProps>);
  });

  return (
    <>
      {clonedChildren}
      {open &&
        createPortal(
          <div
            role="tooltip"
            style={{
              position: "fixed",
              left: pos.x,
              top: pos.y,
              pointerEvents: "none",
              zIndex: 50,
            }}
            className={cn(
              "max-w-sm rounded-md border border-border border-l-2 border-l-warn",
              "bg-bg/95 px-3 py-2 text-sm text-fg shadow-xl backdrop-blur-sm",
              "animate-in fade-in-0",
            )}
          >
            <BlameTooltipBody entry={entry} anchorId={anchorId} />
          </div>,
          document.body,
        )}
    </>
  );
}

/** Rendered body of the blame tooltip. Factored out so the hover
 *  tooltip and any other caller (e.g. a follow-up focus-mode tip)
 *  share the same markup. */
function BlameTooltipBody({
  entry,
  anchorId,
}: {
  entry: AnchorBlameSummaryEntry;
  anchorId: string;
}) {
  const parsed = parseAnchorId(anchorId);
  const scope = parsed?.scope ?? "";
  const humanLabel = anchorHumanLabel(anchorId, null);
  return (
    <div className="flex items-start gap-2">
      <Clock aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warn" />
      <div className="min-w-0">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-warn">
          Blame · {sectionLabel(scope)}
        </div>
        <div className="mt-0.5 truncate font-medium text-fg">{humanLabel}</div>
        <div className="mt-1 text-xs text-muted-fg">
          Last {kindLabel(entry.kind)} {formatRelative(entry.occurred_at)} ·
          backup #{entry.backup_id}
        </div>
        <div className="mt-1 text-[10px] text-muted-fg">
          Click the dot or press{" "}
          <kbd className="rounded border border-border bg-muted/40 px-1 text-[10px]">
            h
          </kbd>{" "}
          for full history
        </div>
      </div>
    </div>
  );
}

/** Persistent click affordance next to anchored rows that have
 *  blame data. Tiny warn-tinted dot; clicking it opens the blame
 *  drawer for that anchor. The hover tooltip now lives on the
 *  row itself (``BlameHoverTooltip``), so the dot no longer carries
 *  its own tooltip — it's a pure click target. */
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
