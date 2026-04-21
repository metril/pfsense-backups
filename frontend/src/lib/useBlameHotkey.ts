import { useEffect, useState } from "react";

/**
 * Shared hook for the ``h``-key blame affordance on pages that
 * render the Structured view (``InstanceHistory`` + ``BackupView``).
 *
 * Caller supplies the anchor tracker (typically ``useFocusedAnchor``
 * or a derived state). Taking it as input — rather than calling
 * ``useFocusedAnchor`` internally — lets pages that already track a
 * focused anchor for other reasons (scroll-sync in ``BackupView``)
 * share one IntersectionObserver instead of mounting two.
 *
 * Listens for the ``h`` key on ``document``; when pressed outside
 * inputs, modals, and with no modifier keys held, opens the blame
 * drawer. If ``focusedAnchor`` is non-null (the common case) it's
 * used directly. If it's null — e.g., the user just loaded the
 * page and hasn't scrolled, or a MutationObserver rebuild briefly
 * cleared the set — a synchronous DOM fallback picks the anchor
 * nearest a reading line 25% down from ``[data-structured-root]``
 * so ``h`` is never a silent no-op. (v0.39.0: this fallback plus
 * the fix in ``useFocusedAnchor`` together fix the "drawer opens
 * once then dies" report.)
 *
 * If neither the tracked anchor nor the DOM fallback finds a
 * candidate (structured root not yet mounted, or zero anchors
 * rendered), ``onNoAnchor`` fires so the caller can surface a
 * toast — preferable to eating the keypress silently.
 *
 * Caller owns the ``AnchorHistoryDrawer`` mount — pass ``blameAnchor``
 * as its ``anchor`` prop and wire ``closeBlame`` to ``onClose``.
 */
export function useBlameHotkey({
  enabled,
  focusedAnchor,
  onNoAnchor,
}: {
  enabled: boolean;
  focusedAnchor: string | null;
  onNoAnchor?: () => void;
}): {
  blameAnchor: string | null;
  openBlame: (anchor: string) => void;
  closeBlame: () => void;
} {
  const [blameAnchor, setBlameAnchor] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return;
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
      if (e.key !== "h") return;
      e.preventDefault();
      const anchor = focusedAnchor ?? findNearestAnchorInDOM();
      if (anchor) {
        setBlameAnchor(anchor);
      } else {
        onNoAnchor?.();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [enabled, focusedAnchor, onNoAnchor]);

  return {
    blameAnchor,
    openBlame: setBlameAnchor,
    closeBlame: () => setBlameAnchor(null),
  };
}

/**
 * DOM fallback for the ``h`` hotkey when the tracked anchor is
 * null. Finds the ``[id^="xref-"] | [id^="field-"]`` element
 * nearest a reading line 25% down from the top of
 * ``[data-structured-root]``. Same heuristic as
 * ``useFocusedAnchor``, so the two agree on which row is "the
 * focused one."
 *
 * Returns null if no structured root is in the DOM or no anchors
 * are rendered — caller surfaces a toast.
 */
function findNearestAnchorInDOM(): string | null {
  const root = document.querySelector<HTMLElement>("[data-structured-root]");
  if (!root) return null;
  const rootRect = root.getBoundingClientRect();
  const readingLine = rootRect.top + rootRect.height * 0.25;
  let best: HTMLElement | null = null;
  let bestDist = Infinity;
  for (const el of root.querySelectorAll<HTMLElement>(
    '[id^="xref-"], [id^="field-"]',
  )) {
    const rect = el.getBoundingClientRect();
    // Only consider anchors that are at least partially inside
    // the root's clip rect — anchors scrolled far away aren't
    // useful fallback candidates.
    if (rect.bottom < rootRect.top || rect.top > rootRect.bottom) continue;
    const dist = Math.abs(rect.top - readingLine);
    if (dist < bestDist) {
      bestDist = dist;
      best = el;
    }
  }
  return best?.id ?? null;
}
