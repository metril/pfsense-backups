import { useEffect } from "react";
import { ArrowLeft } from "lucide-react";
import { expandThenScrollToHash } from "@/lib/xref";
import { useXrefHistory } from "@/components/xref/XrefHistory";
import { Kbd } from "@/components/ui/Kbd";

/**
 * Floating pill that appears at the bottom-right whenever the xref
 * back-stack has at least one entry. Clicking rewinds one step —
 * scrolls back to the origin row and flashes it so the operator
 * re-orients. Also installs a global ``[`` keyboard shortcut as a
 * power-user path (same ``input / modal`` guard the other shortcuts
 * use, so typing into the filter bar doesn't fire it).
 *
 * Intentionally stays mounted (with ``display: none`` when empty)
 * instead of conditionally rendering — otherwise the shortcut
 * listener would install / tear down with every stack transition.
 */
export function XrefBackPill() {
  const history = useXrefHistory();

  // Peek the top BEFORE calling pop so the navigation is driven by
  // the value we can read synchronously. The old "pop returns the
  // popped entry" pattern was lost to React 18's concurrent setState
  // batching — the caller routinely saw ``null`` and silently no-op'd.
  useEffect(() => {
    if (!history) return;
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const inField =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);
      const inModal =
        target?.closest(
          '[role="dialog"], [role="listbox"], [role="menu"]',
        ) != null;
      if (inField || inModal) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "[") {
        e.preventDefault();
        goBack();
      }
    }
    function goBack() {
      if (!history) return;
      const stack = history.stack;
      const entry = stack[stack.length - 1];
      if (!entry) return;
      history.pop();
      expandThenScrollToHash(`#${entry.anchorId}`);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [history]);

  if (!history || history.stack.length === 0) return null;

  const top = history.stack[history.stack.length - 1];
  const onClick = () => {
    history.pop();
    expandThenScrollToHash(`#${top.anchorId}`);
  };

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-40 flex justify-end">
      <button
        type="button"
        onClick={onClick}
        aria-label={`Back to ${top.label}`}
        className="pointer-events-auto inline-flex items-center gap-1.5 rounded-full border border-border bg-bg/95 px-3 py-1.5 text-xs font-medium text-fg shadow-lg backdrop-blur transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
      >
        <ArrowLeft aria-hidden="true" className="h-3.5 w-3.5" />
        <span>
          Back to <span className="text-muted-fg">{top.label}</span>
        </span>
        <Kbd className="ml-1">[</Kbd>
        {history.stack.length > 1 && (
          <span
            className="ml-1 rounded bg-muted px-1 text-[10px] text-muted-fg"
            title={`${history.stack.length} entries on the back stack`}
          >
            {history.stack.length}
          </span>
        )}
      </button>
    </div>
  );
}
