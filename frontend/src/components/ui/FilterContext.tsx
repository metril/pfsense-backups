import {
  createContext,
  useContext,
  useMemo,
  type ReactNode,
} from "react";
import {
  buildMatcher,
  rowHaystack,
  type FilterMatcher,
} from "@/lib/filter";

/**
 * Shares a ``FilterMatcher`` down to every table / section / row that
 * opts into filtering. Components that render rows call
 * ``useFilter()?.item(sectionKey, row)`` and drop the row when it
 * returns ``false``; components that render sections call
 * ``useFilter()?.section(…)``.
 *
 * Design: the provider accepts the raw ``query`` and builds the
 * ``FilterMatcher`` once per query change. The parent page owns the
 * query state (via URL search params) and passes the string in — the
 * context doesn't care about URL sync.
 */

export interface FilterValue {
  query: string;
  active: boolean;
  /** Does this section stay visible at all? ``haystack`` is the
   *  section's title + its indexed labels joined, produced by the
   *  caller (we keep the index-walking out of this module). */
  section: (haystack: string) => boolean;
  /** Does a row inside a visible section stay visible? If the
   *  section title itself matches the query, we return ``true`` for
   *  every row — operators who searched for the section by name want
   *  the whole section. */
  item: (sectionHaystack: string, row: unknown) => boolean;
  /** Low-level matcher for callers that already built their own
   *  haystack (e.g. modified-diff rows needing before+after values). */
  matcher: FilterMatcher;
}

const Ctx = createContext<FilterValue | null>(null);

export function FilterProvider({
  query,
  children,
}: {
  query: string;
  children: ReactNode;
}) {
  const value = useMemo<FilterValue>(() => {
    const matcher = buildMatcher(query);
    return {
      query,
      active: matcher.active,
      matcher,
      section: (haystack: string) => matcher.match(haystack),
      item: (sectionHaystack: string, row: unknown) => {
        if (!matcher.active) return true;
        // Section title match → show all rows. This lets operators
        // search by section name ("aliases") and get every alias,
        // while searching by value ("LAN_NET") narrows to matches.
        if (matcher.match(sectionHaystack)) return true;
        return matcher.match(rowHaystack(row));
      },
    };
  }, [query]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Returns the current filter value, or ``null`` outside a provider.
 *  Tables use this to opt into row-level filtering. */
export function useFilter(): FilterValue | null {
  return useContext(Ctx);
}
