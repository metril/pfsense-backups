import { useEffect, useRef, useState } from "react";

/**
 * Track the nearest visible ``xref-*`` / ``field-*`` element in the
 * currently-rendered Structured view. Used by the Structured ↔ Raw
 * XML tab-switch sync so "current focus" survives a tab toggle.
 *
 * Implementation: IntersectionObserver over every ``[id^="xref-"] |
 * [id^="field-"]`` under the ``[data-structured-root]`` scroll
 * container, tracking the observed element whose top is closest to
 * the container's upper third (same reading-position bias
 * ``useActiveSection`` uses). Only fires when the winner actually
 * changes, so a React state update per scroll frame is avoided.
 *
 * The ``root`` option on IntersectionObserver is load-bearing here:
 * ``[data-structured-root]`` is an ``overflow-auto`` div nested
 * inside a parent with ``overflow-hidden``. Without passing it
 * explicitly, IntersectionObserver defaults to the viewport — but
 * the viewport never scrolls because scroll is confined to the
 * inner div. The observer would then only ever fire on initial
 * mount, making the focused anchor freeze at "whatever row was in
 * viewport when the Structured tab was first shown". (Bug fixed in
 * v0.35.0.)
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

    let observer: IntersectionObserver | null = null;
    let mutator: MutationObserver | null = null;
    let waitObserver: MutationObserver | null = null;
    let rebuildHandle: number | null = null;
    // ``active`` guards against a race where the debounced rebuild
    // fires between the cleanup running and the new observer being
    // installed — rebuild would otherwise re-observe on the
    // just-disconnected observer, silently leaking membership for
    // the next mount cycle.
    let active = true;

    function install(structuredRoot: HTMLElement): void {
      observer = new IntersectionObserver(
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
          root: structuredRoot,
          // "Lead the scroll slightly" bias — row whose top is in
          // the upper third of the scroll root wins. Matches
          // ``useActiveSection``'s heuristic.
          rootMargin: "0px 0px -66% 0px",
          threshold: [0, 0.1, 0.25, 0.5, 1],
        },
      );

      for (const t of structuredRoot.querySelectorAll<HTMLElement>(
        '[id^="xref-"], [id^="field-"]',
      )) {
        observer.observe(t);
      }

      // Filter / navigation churn: the set of rendered anchors
      // changes on every keystroke in the FilterBar. Debounce
      // re-observe into a single tick per idle window.
      const rebuild = () => {
        rebuildHandle = null;
        if (!active || !observer) return;
        observer.disconnect();
        ratios.clear();
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
      observer?.disconnect();
      mutator?.disconnect();
      waitObserver?.disconnect();
    };
  }, [enabled]);

  return anchor;
}
