import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

/**
 * In-app back-navigation stack for cross-reference chips.
 *
 * Each click on an ``<Xref>`` chip in hash-mode (viewer) pushes the
 * origin row onto this stack so the operator can rewind the
 * navigation. The browser's own back button is deliberately left
 * alone — ``expandThenScrollToHash`` uses ``history.replaceState`` so
 * the browser back stack doesn't pollute with hash churn. This
 * provides a parallel, in-app history that only tracks xref-driven
 * jumps.
 *
 * Scope: one stack per ``XrefHistoryProvider`` mount. The viewer
 * mounts one inside each backup-view page; unmounting on backup
 * change clears the stack automatically.
 *
 * Shape: a bounded LIFO (``MAX_DEPTH`` entries). If the user drills
 * deeper than that, the oldest origin drops — unlikely in practice
 * but prevents pathological growth.
 */

const MAX_DEPTH = 32;

export interface XrefBackEntry {
  /** DOM id we should scroll back to (e.g. ``xref-rule-abc``). */
  anchorId: string;
  /** Label shown on the back pill (e.g. ``"alias: RFC1918"`` or
   *  ``"rule #42"``). Derived at push time from the xref index +
   *  DOM, then frozen into the stack entry. */
  label: string;
}

interface XrefHistoryContextValue {
  stack: XrefBackEntry[];
  push: (entry: XrefBackEntry) => void;
  pop: () => XrefBackEntry | null;
  clear: () => void;
}

const Ctx = createContext<XrefHistoryContextValue | null>(null);

export function XrefHistoryProvider({ children }: { children: ReactNode }) {
  const [stack, setStack] = useState<XrefBackEntry[]>([]);

  const push = useCallback((entry: XrefBackEntry) => {
    setStack((prev) => {
      // Collapse consecutive duplicates — re-clicking the same chip
      // twice in a row shouldn't grow the stack.
      const top = prev[prev.length - 1];
      if (top && top.anchorId === entry.anchorId) return prev;
      const next = [...prev, entry];
      if (next.length > MAX_DEPTH) next.splice(0, next.length - MAX_DEPTH);
      return next;
    });
  }, []);

  const pop = useCallback((): XrefBackEntry | null => {
    let popped: XrefBackEntry | null = null;
    setStack((prev) => {
      if (prev.length === 0) return prev;
      popped = prev[prev.length - 1];
      return prev.slice(0, -1);
    });
    return popped;
  }, []);

  const clear = useCallback(() => setStack([]), []);

  const value = useMemo<XrefHistoryContextValue>(
    () => ({ stack, push, pop, clear }),
    [stack, push, pop, clear],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Returns the history API, or ``null`` outside a provider so
 *  callers (like ``<Xref>``) can silently no-op on diff pages or
 *  any other context that doesn't want the stack. */
export function useXrefHistory(): XrefHistoryContextValue | null {
  return useContext(Ctx);
}
