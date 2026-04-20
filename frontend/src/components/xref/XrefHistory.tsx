import {
  createContext,
  useCallback,
  useContext,
  useEffect,
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
 * Persistence: when ``scope`` is provided, the stack is mirrored
 * into ``sessionStorage`` under ``xref-history:${scope}`` so that
 * accidental reloads (or opening devtools and hitting F5) don't
 * erase in-progress drill-downs. Scoped per backup id so switching
 * between backups doesn't bleed stacks. sessionStorage instead of
 * localStorage — the back trail is meaningful for the current
 * browsing session, not forever.
 *
 * Shape: a bounded LIFO (``MAX_DEPTH`` entries). If the user drills
 * deeper than that, the oldest origin drops — unlikely in practice
 * but prevents pathological growth.
 */

const MAX_DEPTH = 32;
const STORAGE_PREFIX = "xref-history:";

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

/** Best-effort restore from sessionStorage. Returns ``[]`` on parse
 *  errors, storage-access errors (private tabs / disabled cookies),
 *  or if the payload shape looks off — the stack is a UX nicety,
 *  not a source of truth, so silent failure is correct. */
function loadStack(scope: string | undefined): XrefBackEntry[] {
  if (!scope || typeof window === "undefined") return [];
  try {
    const raw = window.sessionStorage.getItem(STORAGE_PREFIX + scope);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (e): e is XrefBackEntry =>
        typeof e === "object" &&
        e !== null &&
        typeof (e as XrefBackEntry).anchorId === "string" &&
        typeof (e as XrefBackEntry).label === "string",
    );
  } catch {
    return [];
  }
}

function saveStack(scope: string | undefined, stack: XrefBackEntry[]): void {
  if (!scope || typeof window === "undefined") return;
  try {
    if (stack.length === 0) {
      window.sessionStorage.removeItem(STORAGE_PREFIX + scope);
    } else {
      window.sessionStorage.setItem(
        STORAGE_PREFIX + scope,
        JSON.stringify(stack),
      );
    }
  } catch {
    // sessionStorage can throw on quota / private-tab errors — ignore.
  }
}

export function XrefHistoryProvider({
  children,
  scope,
}: {
  children: ReactNode;
  /** Per-backup namespace for sessionStorage (e.g. ``view:42``).
   *  Leave undefined to disable persistence. */
  scope?: string;
}) {
  const [stack, setStack] = useState<XrefBackEntry[]>(() => loadStack(scope));

  // When the scope changes (operator navigates to a different
  // backup), swap the stack out for that backup's saved state.
  useEffect(() => {
    setStack(loadStack(scope));
  }, [scope]);

  // Mirror every stack mutation to sessionStorage. The effect
  // captures the CURRENT scope, so writes during a scope change
  // land in the new bucket (intentional — the setStack above
  // re-seeds first).
  useEffect(() => {
    saveStack(scope, stack);
  }, [scope, stack]);

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
