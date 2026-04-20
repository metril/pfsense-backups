import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { Search, X } from "lucide-react";
import { Kbd } from "@/components/ui/Kbd";
import { cn } from "@/lib/cn";
import { groupClasses } from "@/lib/sectionGroup";
import {
  allTargets,
  expandThenScrollToHash,
  type XrefTarget,
} from "@/lib/xref";
import { useXrefIndex } from "@/components/xref/XrefContext";

/**
 * Fuzzy command palette over every referenceable object in the current
 * config. Triggered by ``/`` at the document level; ``Esc`` dismisses;
 * ``Enter`` jumps to the selected target and plays the flash animation.
 *
 * Matching is a simple subsequence-contains on the concatenated
 * ``label + kind + secondary`` string — fast enough for O(n) across the
 * typical ~hundreds of targets in a real pfSense config. Selection
 * is keyboard-only (Up/Down/Enter/Esc); click works too.
 */
export function QuickJump() {
  const index = useXrefIndex();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      // Ignore when the user is already typing in a form field, so
      // ``/`` still works inside their own inputs.
      const target = e.target as HTMLElement | null;
      const inField =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);
      if (e.key === "/" && !inField && !open) {
        e.preventDefault();
        setOpen(true);
      } else if (e.key === "Escape" && open) {
        setOpen(false);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    if (open) {
      // Let the backdrop mount before focusing.
      requestAnimationFrame(() => inputRef.current?.focus());
      setQuery("");
      setSelected(0);
    }
  }, [open]);

  const allTargetList = useMemo(
    () => (index ? allTargets(index) : []),
    [index],
  );

  const results = useMemo(() => {
    if (!query.trim()) return allTargetList.slice(0, 50);
    const needle = query.toLowerCase();
    const scored = allTargetList
      .map((t) => {
        const hay = `${t.label} ${t.kind} ${t.secondary ?? ""} ${t.key}`.toLowerCase();
        const idx = hay.indexOf(needle);
        return idx >= 0 ? { t, score: idx } : null;
      })
      .filter((x): x is { t: XrefTarget; score: number } => x !== null)
      .sort((a, b) => a.score - b.score || a.t.label.localeCompare(b.t.label));
    return scored.slice(0, 50).map((x) => x.t);
  }, [query, allTargetList]);

  useEffect(() => {
    // Keep selection in range whenever results change.
    setSelected((s) => Math.min(s, Math.max(0, results.length - 1)));
  }, [results.length]);

  function pick(t: XrefTarget) {
    setOpen(false);
    // Allow the backdrop to unmount before the scroll — scrolling
    // while a fixed-position modal is painted produces jank. Use
    // expandThenScrollToHash so collapsed target cards auto-open
    // via the DeepLinkBridge before the scroll fires.
    requestAnimationFrame(() => expandThenScrollToHash(`#${t.anchorId}`));
  }

  function onInputKeyDown(e: ReactKeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelected((s) => Math.min(s + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelected((s) => Math.max(s - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const t = results[selected];
      if (t) pick(t);
    }
  }

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Jump to config object"
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-24"
      onClick={(e) => {
        if (e.target === e.currentTarget) setOpen(false);
      }}
    >
      <div className="w-full max-w-xl rounded border border-border bg-bg shadow-2xl">
        <div className="flex items-center gap-2 border-b border-border px-3 py-2">
          <Search aria-hidden="true" className="h-4 w-4 text-muted-fg" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelected(0);
            }}
            onKeyDown={onInputKeyDown}
            placeholder="Jump to interface, CA, rule, pool…"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-fg"
            aria-label="Jump to object name"
          />
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="text-muted-fg hover:text-fg"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <ul className="max-h-80 overflow-y-auto py-1" role="listbox">
          {results.length === 0 ? (
            <li className="px-3 py-2 text-sm text-muted-fg">No matches.</li>
          ) : (
            results.map((t, i) => {
              const gc = groupClasses(t.group);
              const active = i === selected;
              return (
                <li
                  key={`${t.kind}-${t.key}`}
                  role="option"
                  aria-selected={active}
                  className={cn(
                    "flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm",
                    active ? "bg-muted" : "hover:bg-muted/50",
                  )}
                  onClick={() => pick(t)}
                  onMouseEnter={() => setSelected(i)}
                >
                  <span
                    className={cn(
                      "inline-flex min-w-[6.5rem] items-center justify-center rounded border px-1.5 py-0.5 text-[10px] uppercase",
                      gc.title,
                      gc.chipBorder,
                    )}
                  >
                    {t.kind.replace(/_/g, " ")}
                  </span>
                  <span className="font-medium">{t.label}</span>
                  {t.secondary && (
                    <span className="truncate text-muted-fg text-xs">
                      {t.secondary}
                    </span>
                  )}
                </li>
              );
            })
          )}
        </ul>
        <div className="flex items-center justify-between border-t border-border px-3 py-1.5 text-[11px] text-muted-fg">
          <div className="flex items-center gap-1">
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd>
            to navigate
          </div>
          <div className="flex items-center gap-1">
            <Kbd>Enter</Kbd> to jump
            <span className="mx-1">·</span>
            <Kbd>Esc</Kbd> to close
          </div>
        </div>
      </div>
    </div>
  );
}
