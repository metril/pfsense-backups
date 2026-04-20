import { useSyncExternalStore } from "react";

/**
 * Subscribes a component to a CSS media query. Returns whether the
 * query currently matches and re-renders when the match state flips.
 *
 * Use case: switching layout between horizontal ToC (narrow viewports)
 * and sticky sidebar (wide viewports). Thin wrapper over
 * ``window.matchMedia`` using React 18's ``useSyncExternalStore`` to
 * stay tearing-free across concurrent renders.
 *
 * SSR-safe: the server-snapshot branch returns ``false`` so the initial
 * client render can hydrate without layout thrash — the effect then
 * syncs to the real media-query state on mount.
 */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (cb) => {
      if (typeof window === "undefined") return () => {};
      const mql = window.matchMedia(query);
      mql.addEventListener("change", cb);
      return () => mql.removeEventListener("change", cb);
    },
    () => {
      if (typeof window === "undefined") return false;
      return window.matchMedia(query).matches;
    },
    () => false,
  );
}
