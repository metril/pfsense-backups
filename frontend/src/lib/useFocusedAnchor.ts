import { useEffect, useRef, useState } from "react";

/**
 * Track the nearest visible ``xref-*`` / ``field-*`` element in the
 * currently-rendered Structured view. Used by the Structured ↔ Raw
 * XML tab-switch sync so "current focus" survives a tab toggle, and
 * by the blame drawer so ``h`` opens history for the row the
 * operator is reading.
 *
 * Implementation: IntersectionObserver maintains a Set of anchors
 * currently inside the ``[data-structured-root]`` scroll container;
 * a scroll listener (rAF-throttled) picks the anchor whose top
 * ``getBoundingClientRect().top`` is closest to a reading line 25%
 * down from the root's top edge. That "closest to reading line"
 * heuristic replaces the previous "highest intersectionRatio"
 * picker — with many short pfSense rows simultaneously visible, all
 * of them tied at ratio 1.0 and the first-in-DOM-order won every
 * tie, leaving ``focusedAnchor`` stuck on the topmost row as the
 * operator scrolled through the band. (Bug fix in v0.39.0.)
 *
 * The ``root`` option on IntersectionObserver is load-bearing here:
 * ``[data-structured-root]`` is an ``overflow-auto`` div nested
 * inside a parent with ``overflow-hidden``. Without passing it
 * explicitly, IntersectionObserver defaults to the viewport — but
 * the viewport never scrolls because scroll is confined to the
 * inner div. (Bug fixed in v0.35.0.)
 *
 * ``enabled`` — pass ``false`` to disable observation (e.g. the Raw
 * XML tab is active). Saves the observer cost when no consumer
 * cares.
 */
export function useFocusedAnchor(enabled: boolean): string | null {
  const [anchor, setAnchor] = useState<string | null>(null);
  const visibleRef = useRef<Set<HTMLElement>>(new Set());
  // Stable-callback pattern: store the latest setter so the
  // observer callback doesn't capture a stale closure if the
  // component re-renders while observing.
  const emitRef = useRef((next: string | null) => setAnchor(next));
  emitRef.current = (next) => setAnchor((prev) => (prev === next ? prev : next));

  useEffect(() => {
    // Capture the Set instance once so the cleanup path references
    // the same object that the observer callbacks wrote to —
    // satisfies react-hooks/exhaustive-deps' "ref may have changed
    // by cleanup time" warning (it can't here, since useRef's
    // identity is stable, but the lint can't prove that).
    const visible = visibleRef.current;
    if (!enabled) {
      setAnchor(null);
      visible.clear();
      return;
    }
    if (typeof window === "undefined" || !("IntersectionObserver" in window)) {
      return;
    }
    visible.clear();

    let observer: IntersectionObserver | null = null;
    let mutator: MutationObserver | null = null;
    let waitObserver: MutationObserver | null = null;
    let rebuildHandle: number | null = null;
    let scrollRaf: number | null = null;
    let scrollCleanup: (() => void) | null = null;
    // ``active`` guards against a race where the debounced rebuild
    // fires between the cleanup running and the new observer being
    // installed — rebuild would otherwise re-observe on the
    // just-disconnected observer, silently leaking membership for
    // the next mount cycle.
    let active = true;

    function install(structuredRoot: HTMLElement): void {
      const recompute = () => {
        const rootRect = structuredRoot.getBoundingClientRect();
        // Reading-line 25% down from the top edge — matches the
        // ``useActiveSection`` heuristic. Picking the anchor whose
        // top is closest to this line maps to "the row I just
        // scrolled into view".
        const readingLine = rootRect.top + rootRect.height * 0.25;
        let best: HTMLElement | null = null;
        let bestDist = Infinity;
        for (const el of visible) {
          const dist = Math.abs(el.getBoundingClientRect().top - readingLine);
          if (dist < bestDist) {
            bestDist = dist;
            best = el;
          }
        }
        emitRef.current(best ? best.id : null);
      };

      observer = new IntersectionObserver(
        (entries) => {
          for (const e of entries) {
            const el = e.target as HTMLElement;
            if (e.isIntersecting) visible.add(el);
            else visible.delete(el);
          }
          recompute();
        },
        { root: structuredRoot, threshold: 0 },
      );

      for (const t of structuredRoot.querySelectorAll<HTMLElement>(
        '[id^="xref-"], [id^="field-"]',
      )) {
        observer.observe(t);
      }

      // IntersectionObserver only fires when elements cross the
      // root's viewport edge — so mid-viewport scrolling between
      // two already-intersecting anchors wouldn't update the
      // winner. A rAF-throttled scroll listener re-runs the
      // reading-line pick on every scroll tick. Cheap: the set is
      // typically <20 elements.
      const onScroll = () => {
        if (scrollRaf !== null) return;
        scrollRaf = requestAnimationFrame(() => {
          scrollRaf = null;
          recompute();
        });
      };
      structuredRoot.addEventListener("scroll", onScroll, { passive: true });
      scrollCleanup = () => {
        structuredRoot.removeEventListener("scroll", onScroll);
        if (scrollRaf !== null) {
          cancelAnimationFrame(scrollRaf);
          scrollRaf = null;
        }
      };

      // Filter / navigation churn: the set of rendered anchors
      // changes on every keystroke in the FilterBar. Debounce
      // re-observe into a single tick per idle window. We prune
      // detached nodes from the visible set so stale entries don't
      // leak across rebuild cycles.
      const rebuild = () => {
        rebuildHandle = null;
        if (!active || !observer) return;
        observer.disconnect();
        for (const el of [...visible]) {
          if (!structuredRoot.contains(el)) visible.delete(el);
        }
        for (const t of structuredRoot.querySelectorAll<HTMLElement>(
          '[id^="xref-"], [id^="field-"]',
        )) {
          observer.observe(t);
        }
      };
      mutator = new MutationObserver(() => {
        if (rebuildHandle !== null) return;
        rebuildHandle = window.setTimeout(rebuild, 50);
      });
      mutator.observe(structuredRoot, { childList: true, subtree: true });
    }

    const initialRoot = document.querySelector<HTMLElement>(
      "[data-structured-root]",
    );
    if (initialRoot) {
      install(initialRoot);
    } else {
      // Lazy-loaded ParsedBackupView hasn't mounted yet (Suspense
      // fallback still showing). Watch for it to arrive.
      waitObserver = new MutationObserver(() => {
        const root = document.querySelector<HTMLElement>(
          "[data-structured-root]",
        );
        if (root && active) {
          waitObserver?.disconnect();
          waitObserver = null;
          install(root);
        }
      });
      waitObserver.observe(document.body, {
        childList: true,
        subtree: true,
      });
    }

    return () => {
      active = false;
      if (rebuildHandle !== null) {
        window.clearTimeout(rebuildHandle);
      }
      scrollCleanup?.();
      observer?.disconnect();
      mutator?.disconnect();
      waitObserver?.disconnect();
      visible.clear();
    };
  }, [enabled]);

  return anchor;
}
