import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

/**
 * Broadcast channel that lets a parent page drive every ``<Card>``
 * underneath it open or closed in one gesture. Each Card watches the
 * context's ``resetVersion``; when it ticks, the Card snaps its local
 * open/closed state to whatever ``snapTo`` is set to.
 *
 * The version-number pattern (instead of just a boolean) means a
 * user can expand-all, manually collapse one card, and expand-all
 * again — the second expand-all still fires because ``resetVersion``
 * changes even though ``snapTo`` stays ``true``.
 *
 * Also carries the persistence scope for the sessionStorage key used
 * by each Card to remember its open/closed state across navigations.
 * Scope is something like ``view:123`` or ``diff:5-7`` so two backups
 * don't share state.
 */
interface CardGroupState {
  resetVersion: number;
  snapTo: boolean;
  expandAll: () => void;
  collapseAll: () => void;
  /** Namespace prefix for sessionStorage keys (e.g. ``"view:42"``).
   *  ``null`` disables persistence. */
  scope: string | null;
}

const Ctx = createContext<CardGroupState | null>(null);

export function CardGroupProvider({
  scope,
  children,
}: {
  scope: string | null;
  children: ReactNode;
}) {
  const [resetVersion, setResetVersion] = useState(0);
  const [snapTo, setSnapTo] = useState(true);

  const expandAll = useCallback(() => {
    setSnapTo(true);
    setResetVersion((v) => v + 1);
  }, []);

  const collapseAll = useCallback(() => {
    setSnapTo(false);
    setResetVersion((v) => v + 1);
  }, []);

  const value = useMemo<CardGroupState>(
    () => ({ resetVersion, snapTo, expandAll, collapseAll, scope }),
    [resetVersion, snapTo, expandAll, collapseAll, scope],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Returns the current state or ``null`` outside a provider. Cards use
 *  this to opt into broadcast-driven behaviour; uses outside a
 *  provider retain their local-only pre-v0.14 state. */
export function useCardGroup(): CardGroupState | null {
  return useContext(Ctx);
}

/** Helper for the expand/collapse-all buttons: hands callers a
 *  already-scoped hook so the button component doesn't need to
 *  null-check. */
export function useCardGroupActions(): {
  expandAll: () => void;
  collapseAll: () => void;
} | null {
  const ctx = useContext(Ctx);
  if (!ctx) return null;
  return { expandAll: ctx.expandAll, collapseAll: ctx.collapseAll };
}
