import { useEffect, useState } from "react";

/**
 * Watches a page's ``<section id="...">`` elements via
 * ``IntersectionObserver`` and returns the id of the one that's
 * currently most visible near the top of the viewport.
 *
 * Used by the sticky ToC sidebar on wide viewports to highlight the
 * section the operator is currently reading. The ``rootMargin`` is
 * tuned to bias toward the section whose top is in the upper third of
 * the viewport, which prevents flicker when two sections straddle the
 * middle — without this, scrolling slowly between two adjacent
 * sections makes the highlight bounce.
 *
 * ``prefix`` filters candidate elements by id prefix so the viewer
 * (``"section-"``) and the diff (``"diff-"``) can share one hook.
 * Pass ``null`` to disable (e.g. on narrow viewports where the sticky
 * sidebar isn't rendered — no need to pay for the observer).
 *
 * ``version`` is a hint to rebuild the observer — pass any value
 * whose identity changes when the set of rendered sections changes
 * (filter apply, filter clear, a fresh config arriving). Without
 * this, sections that mount AFTER the observer was set up are
 * invisible to it, so the sidebar highlight goes stale after a
 * filter change.
 *
 * Accepts ``string | number`` so callers can pass the raw filter
 * query. A naive visible-count proxy was previously used here, but
 * that collides when two different filters happen to leave the same
 * number of sections visible (different sections, same count) and
 * the observer wouldn't rebuild.
 */
export function useActiveSection(
  prefix: string | null,
  version: string | number = 0,
): string | null {
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    if (!prefix) {
      setActiveId(null);
      return;
    }
    if (typeof window === "undefined" || !("IntersectionObserver" in window))
      return;

    // Reset on every rebuild. Previously, when a filter hid every
    // section (targets.length === 0) the effect returned early without
    // clearing the stale id, leaving the sidebar highlighting a
    // section that no longer existed in the DOM. Clearing up front
    // keeps the sidebar honest until the observer produces the next
    // real intersection.
    setActiveId(null);

    const targets = Array.from(
      document.querySelectorAll<HTMLElement>(`[id^="${prefix}"]`),
    );
    if (targets.length === 0) return;

    // Track every observed id's latest intersection ratio, then pick
    // the highest. A plain "most visible" comparison would pick the
    // one straddling the center; the top-third margin shifts the
    // decision earlier so the sidebar "leads" the scroll slightly.
    const ratios = new Map<string, number>();
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
        if (bestRatio > 0) setActiveId(bestId);
      },
      {
        // Ignore the bottom two-thirds so "active" tracks the section
        // whose top edge has just crossed into the visible area.
        rootMargin: "0px 0px -66% 0px",
        threshold: [0, 0.1, 0.25, 0.5, 1],
      },
    );

    for (const t of targets) observer.observe(t);
    return () => observer.disconnect();
  }, [prefix, version]);

  return activeId;
}
