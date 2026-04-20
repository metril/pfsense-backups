import { Alert } from "@/components/ui/Alert";
import { useFilter } from "@/components/ui/FilterContext";

/**
 * Renders a banner when the URL carries a hash that points at content
 * hidden by the active filter.
 *
 * Decision tree on each render:
 *   1. No filter active → nothing.
 *   2. No hash in URL → nothing.
 *   3. Hash doesn't match one of our known prefixes
 *      (``xref-``, ``section-``, ``diff-``) → nothing. This
 *      suppresses false positives on random/typo hashes that would
 *      never resolve to anything regardless of the filter.
 *   4. Element with that id exists in the DOM → nothing (already
 *      reachable; no banner needed).
 *   5. Otherwise → show the banner with a Clear Filter button.
 *
 *  The dead-link false-positive is the historical wart: without the
 *  prefix gate at step 3, pasting a garbled ``#anything`` while a
 *  filter happens to be active produced a misleading "hidden by your
 *  filter" banner for content that never existed. */
export function FilterHiddenAnchorBanner({
  onClear,
}: {
  onClear: () => void;
}) {
  const filter = useFilter();
  const hash = typeof window === "undefined" ? "" : window.location.hash;
  if (!filter?.active || !hash) return null;
  const id = hash.slice(1);
  // Accept only anchors we're known to emit. Anything else is a bad
  // link (typo, stale fragment, external deep link with a naming
  // convention we don't own) — not a filter-hidden target.
  const looksLikeOurs =
    id.startsWith("xref-") ||
    id.startsWith("section-") ||
    id.startsWith("diff-");
  if (!looksLikeOurs) return null;
  if (typeof document !== "undefined" && document.getElementById(id))
    return null;
  return (
    <Alert tone="warn" title="Anchor hidden by filter" className="mb-2">
      The link you followed points at content that is hidden by your
      current filter.{" "}
      <button
        type="button"
        onClick={onClear}
        className="font-medium underline hover:text-fg"
      >
        Clear filter
      </button>
      {" to see it."}
    </Alert>
  );
}
