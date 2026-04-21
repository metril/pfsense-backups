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
 * drawer for ``focusedAnchor``.
 *
 * Caller owns the ``AnchorHistoryDrawer`` mount — pass ``blameAnchor``
 * as its ``anchor`` prop and wire ``closeBlame`` to ``onClose``.
 */
export function useBlameHotkey({
  enabled,
  focusedAnchor,
}: {
  enabled: boolean;
  focusedAnchor: string | null;
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
      if (e.key === "h" && focusedAnchor) {
        e.preventDefault();
        setBlameAnchor(focusedAnchor);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [enabled, focusedAnchor]);

  return {
    blameAnchor,
    openBlame: setBlameAnchor,
    closeBlame: () => setBlameAnchor(null),
  };
}
