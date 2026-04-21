import { useEffect, useRef, useState } from "react";

/**
 * Track the nearest visible ``xref-*`` / ``field-*`` element in the
 * currently-rendered Structured view. Used by the Structured ↔ Raw
 * XML tab-switch sync so "current focus" survives a tab toggle.
 *
 * Implementation: IntersectionObserver over every ``[id^="xref-"] |
 * [id^="field-"]`` in the document, tracking the observed element
 * whose top is closest to the viewport's upper third (the same
 * reading-position bias ``useActiveSection`` uses). Only fires when
 * the winner actually changes, so a React state update per scroll
 * frame is avoided.
 *
 * ``enabled`` — pass ``false`` to disable observation (e.g. the Raw
 * XML tab is active). Saves the observer cost when no consumer
 * cares.
 */
export function useFocusedAnchor(enabled: boolean): string | null {
  const [anchor, setAnchor] = useState<string | null>(null);
  const ratiosRef = useRef<Map<string, number>>(new Map());
  // Stable-callback pattern: store the latest setter so the
  // observer callback doesn't capture a stale closure if the
  // component re-renders while observing.
  const emitRef = useRef((next: string | null) => setAnchor(next));
  emitRef.current = (next) => setAnchor((prev) => (prev === next ? prev : next));

  useEffect(() => {
    if (!enabled) {
      setAnchor(null);
      ratiosRef.current.clear();
      return;
    }
    if (typeof window === "undefined" || !("IntersectionObserver" in window)) {
      return;
    }
    const ratios = ratiosRef.current;
    ratios.clear();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          ratios.set(e.target.id, e.intersectionRatio);
        }
        let bestId: string | null = null;
        let bestRatio = -1;
        for (const [id, r] of ratios.entries()) {
          if (r > bestRatio) {
            bestRatio = r;
            bestId = id;
          }
        }
        emitRef.current(bestRatio > 0 ? bestId : null);
      },
      {
        // Same "lead the scroll slightly" bias as ``useActiveSection``
        // — the section / row whose top is in the upper third of the
        // viewport wins.
        rootMargin: "0px 0px -66% 0px",
        threshold: [0, 0.1, 0.25, 0.5, 1],
      },
    );

    const targets = document.querySelectorAll<HTMLElement>(
      '[id^="xref-"], [id^="field-"]',
    );
    for (const t of targets) observer.observe(t);

    // Filter changes / navigation can swap the set of rendered
    // anchors. Re-observe when the DOM shape under the main content
    // container mutates. Narrow the root to avoid pathological
    // churn — mutations outside the structured scroll container
    // don't matter. Debounce: typing into the filter bar produces
    // dozens of child mutations per keystroke, each of which would
    // rebuild observer membership across hundreds of anchors. Batch
    // into a single re-observe per idle tick.
    const mutationRoot = document.querySelector<HTMLElement>(
      "[data-structured-root]",
    );
    let rebuildHandle: number | null = null;
    const rebuild = () => {
      rebuildHandle = null;
      const next = document.querySelectorAll<HTMLElement>(
        '[id^="xref-"], [id^="field-"]',
      );
      observer.disconnect();
      ratios.clear();
      for (const t of next) observer.observe(t);
    };
    const mutator = new MutationObserver(() => {
      if (rebuildHandle !== null) return;
      rebuildHandle = window.setTimeout(rebuild, 50);
    });
    if (mutationRoot) {
      mutator.observe(mutationRoot, { childList: true, subtree: true });
    }

    return () => {
      if (rebuildHandle !== null) {
        window.clearTimeout(rebuildHandle);
      }
      observer.disconnect();
      mutator.disconnect();
    };
  }, [enabled]);

  return anchor;
}
