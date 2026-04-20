/**
 * Shared matcher for the in-view filter bar.
 *
 * Behaviour:
 * - Whitespace-tokenised; AND semantics across tokens; case-insensitive
 *   substring per token. Typing ``"lan rule"`` matches haystacks that
 *   contain both ``"lan"`` and ``"rule"`` in any order.
 * - Empty / whitespace query → ``match()`` returns ``true`` for every
 *   input. Callers never need to check ``query`` explicitly.
 *
 * Design note: we intentionally don't do fuzzy scoring here. The
 * operator's use case is "hide noise I don't care about," not
 * "rank-search across everything." QuickJump (``/``) already handles
 * the latter with its own position-ranked substring matcher.
 */
export interface FilterMatcher {
  /** The raw user input — used for empty-state messaging and the
   *  "your anchor is filter-hidden" banner. */
  query: string;
  /** ``true`` iff every whitespace-separated token in ``query``
   *  appears as a case-insensitive substring of ``hay``. Empty
   *  query always matches. */
  match(hay: string): boolean;
  /** Convenience: always ``false`` for empty queries, ``true`` when
   *  the user has typed anything non-whitespace. */
  active: boolean;
}

export function buildMatcher(query: string): FilterMatcher {
  const tokens = query
    .toLowerCase()
    .split(/\s+/)
    .filter((t) => t.length > 0);
  const active = tokens.length > 0;
  const match = (hay: string): boolean => {
    if (!active) return true;
    const h = hay.toLowerCase();
    for (const t of tokens) {
      if (!h.includes(t)) return false;
    }
    return true;
  };
  return { query, match, active };
}

/** Extract all flat string-valued field contents from a row object
 *  so the item-level filter has something to match against. Used by
 *  table renderers that opt into item-level filtering. Accepts
 *  ``unknown`` (not ``Record<string, unknown>``) so the parser's
 *  typed interfaces — which don't carry a string index signature —
 *  pass without noise. */
export function rowHaystack(row: unknown): string {
  if (!row || typeof row !== "object") return "";
  const parts: string[] = [];
  for (const v of Object.values(row as Record<string, unknown>)) {
    if (typeof v === "string") parts.push(v);
    else if (typeof v === "number" || typeof v === "boolean")
      parts.push(String(v));
    else if (Array.isArray(v)) {
      for (const el of v) {
        if (typeof el === "string") parts.push(el);
        else if (typeof el === "number" || typeof el === "boolean")
          parts.push(String(el));
      }
    }
  }
  return parts.join(" ");
}
