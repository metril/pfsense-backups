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

/** Extract all string-valued field contents from a row object so the
 *  item-level filter has something to match against. Walks nested
 *  objects one level deep so struct-valued sub-fields — ``Endpoint``
 *  on ``FirewallRule`` / ``NatRule``, nested ``Gateway.monitor``, etc.
 *  — contribute to the haystack. Without the recursion, filtering for
 *  ``192.168.1.0`` inside a rule's ``source.address`` silently missed.
 *
 *  One-level depth is enough for every row type the parser emits;
 *  deeper recursion would only serve to include RawSection XML which
 *  is already searchable via the Raw XML tab. Cycles can't occur
 *  because Pydantic models are tree-shaped. */
export function rowHaystack(row: unknown): string {
  if (!row || typeof row !== "object") return "";
  const parts: string[] = [];
  const pushScalar = (v: unknown): void => {
    if (typeof v === "string") parts.push(v);
    else if (typeof v === "number" || typeof v === "boolean")
      parts.push(String(v));
  };
  for (const v of Object.values(row as Record<string, unknown>)) {
    if (v === null || v === undefined) continue;
    if (Array.isArray(v)) {
      for (const el of v) {
        if (el && typeof el === "object" && !Array.isArray(el)) {
          // Array of objects — flatten one level.
          for (const inner of Object.values(el as Record<string, unknown>)) {
            pushScalar(inner);
          }
        } else {
          pushScalar(el);
        }
      }
    } else if (typeof v === "object") {
      // Nested object (e.g. Endpoint) — flatten its scalar + array
      // children. Do NOT recurse further; avoids accidentally pulling
      // in enormous sub-trees like RawSection.
      for (const inner of Object.values(v as Record<string, unknown>)) {
        if (Array.isArray(inner)) {
          for (const el of inner) pushScalar(el);
        } else {
          pushScalar(inner);
        }
      }
    } else {
      pushScalar(v);
    }
  }
  return parts.join(" ");
}
