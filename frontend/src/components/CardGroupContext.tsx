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
 * Targeted open (``snapTarget(id)``): used by deep-link handling when
 * the URL hash points at an element inside a collapsed card. Only the
 * matching card reacts; the rest retain their state. Version-numbered
 * for the same reason as above — a second call with the same id still
 * fires.
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
  /** Incremented every time ``snapTarget`` is called. Cards watch this
   *  and open themselves if ``snapTargetId`` matches their own id. */
  snapTargetVersion: number;
  snapTargetId: string | null;
  snapTarget: (cardId: string) => void;
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
  const [snapTargetVersion, setSnapTargetVersion] = useState(0);
  const [snapTargetId, setSnapTargetId] = useState<string | null>(null);

  const expandAll = useCallback(() => {
    setSnapTo(true);
    setResetVersion((v) => v + 1);
  }, []);

  const collapseAll = useCallback(() => {
    setSnapTo(false);
    setResetVersion((v) => v + 1);
  }, []);

  const snapTarget = useCallback((cardId: string) => {
    setSnapTargetId(cardId);
    setSnapTargetVersion((v) => v + 1);
  }, []);

  const value = useMemo<CardGroupState>(
    () => ({
      resetVersion,
      snapTo,
      expandAll,
      collapseAll,
      snapTargetVersion,
      snapTargetId,
      snapTarget,
      scope,
    }),
    [
      resetVersion,
      snapTo,
      expandAll,
      collapseAll,
      snapTargetVersion,
      snapTargetId,
      snapTarget,
      scope,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Returns the current state or ``null`` outside a provider. Cards use
 *  this to opt into broadcast-driven behaviour; uses outside a
 *  provider retain their local-only pre-v0.14 state. */
export function useCardGroup(): CardGroupState | null {
  return useContext(Ctx);
}

/** Helper for the expand/collapse-all buttons. Memoises the returned
 *  object so callers that put it in a ``useEffect`` dep array don't
 *  reinstall the effect on every render — important for the keydown
 *  listener in ``ExpandCollapseAll``, which was previously thrashing. */
export function useCardGroupActions(): {
  expandAll: () => void;
  collapseAll: () => void;
  snapTarget: (cardId: string) => void;
} | null {
  const ctx = useContext(Ctx);
  return useMemo(() => {
    if (!ctx) return null;
    return {
      expandAll: ctx.expandAll,
      collapseAll: ctx.collapseAll,
      snapTarget: ctx.snapTarget,
    };
  }, [ctx?.expandAll, ctx?.collapseAll, ctx?.snapTarget]);
}
