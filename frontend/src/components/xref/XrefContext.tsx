import { createContext, useContext, useMemo, type ReactNode } from "react";
import type { ParsedConfig } from "@/api/parsedTypes";
import { buildIndex, type XrefIndex } from "@/lib/xref";

/**
 * Carries the current xref index down the render tree so every ``<Xref>``
 * chip can resolve references without prop-drilling through thirty section
 * tables. The provider memoises on the parsed-config object identity — the
 * TanStack Query cache hands us the same ``ParsedConfig`` between renders
 * unless a fresh backup lands, so this effectively runs ``buildIndex``
 * exactly once per backup.
 */
const Ctx = createContext<XrefIndex | null>(null);

export function XrefProvider({
  data,
  children,
}: {
  data: ParsedConfig;
  children: ReactNode;
}) {
  const index = useMemo(() => buildIndex(data), [data]);
  return <Ctx.Provider value={index}>{children}</Ctx.Provider>;
}

/** Returns the current index, or ``null`` if rendered outside a provider
 *  (chips degrade to plain text in that case — see ``Xref.tsx``). */
export function useXrefIndex(): XrefIndex | null {
  return useContext(Ctx);
}
