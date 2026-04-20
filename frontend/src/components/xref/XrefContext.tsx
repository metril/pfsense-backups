import { createContext, useContext, useMemo, type ReactNode } from "react";
import type { ParsedConfig } from "@/api/parsedTypes";
import { buildIndex, type XrefIndex } from "@/lib/xref";

/**
 * Carries xref indexes down the render tree so ``<Xref>`` chips resolve
 * references without prop-drilling through thirty section tables.
 *
 * Two modes of operation:
 * - **Viewer** (single backup): one provider, one index, chips render
 *   hash hrefs that scroll in-page.
 * - **Diff** (two backups): two stacked providers tagged ``side="old"``
 *   and ``side="new"``. A chip with ``side="old"`` resolves against the
 *   old provider and renders a route href pointing at the old backup's
 *   viewer page; same for ``side="new"``. A chip without a ``side``
 *   prop falls back to the nearest provider (viewer behavior stays
 *   byte-identical).
 *
 * The provider memoises on the parsed-config identity — the TanStack
 * Query cache hands us the same ``ParsedConfig`` between renders unless
 * a fresh backup lands, so ``buildIndex`` effectively runs once per
 * backup.
 */

export type XrefSide = "old" | "new";
export type XrefHrefMode = "hash" | "route";

export interface XrefProviderEntry {
  index: XrefIndex;
  hrefMode: XrefHrefMode;
  /** Needed for route-mode href construction. */
  backupId?: number;
}

interface XrefContextValue {
  /** Keyed by ``"default"`` (nearest) plus optionally ``"old"`` /
   *  ``"new"`` when the provider tagged itself with a side. */
  entries: Map<"default" | XrefSide, XrefProviderEntry>;
}

const Ctx = createContext<XrefContextValue | null>(null);

export function XrefProvider({
  data,
  side,
  hrefMode = "hash",
  backupId,
  children,
}: {
  data: ParsedConfig;
  side?: XrefSide;
  hrefMode?: XrefHrefMode;
  backupId?: number;
  children: ReactNode;
}) {
  const parent = useContext(Ctx);
  const entry = useMemo<XrefProviderEntry>(
    () => ({ index: buildIndex(data), hrefMode, backupId }),
    [data, hrefMode, backupId],
  );
  const value = useMemo<XrefContextValue>(() => {
    const entries = new Map(parent?.entries ?? []);
    entries.set("default", entry);
    if (side) entries.set(side, entry);
    return { entries };
  }, [parent, entry, side]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Returns the provider entry matching ``side`` (falling back to the
 *  nearest provider), or ``null`` outside any provider. Chips reach for
 *  this when they need the hrefMode / backupId in addition to the
 *  index; most call sites just use ``useXrefIndex``. */
export function useXrefEntry(side?: XrefSide): XrefProviderEntry | null {
  const ctx = useContext(Ctx);
  if (!ctx) return null;
  if (side) return ctx.entries.get(side) ?? ctx.entries.get("default") ?? null;
  return ctx.entries.get("default") ?? null;
}

/** Convenience wrapper for callers that only care about the index —
 *  preserves the viewer's pre-v0.15 API. */
export function useXrefIndex(side?: XrefSide): XrefIndex | null {
  return useXrefEntry(side)?.index ?? null;
}
