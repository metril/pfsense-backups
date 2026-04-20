import { useEffect, useRef } from "react";
import { Search, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { Input } from "@/components/ui/Input";
import { Kbd } from "@/components/ui/Kbd";

/**
 * Filter input — the top-of-page control that narrows visible sections
 * and rows to those matching the operator's query. Pure presentational;
 * the parent page owns the query string (synced with ``?filter=``).
 *
 * Keyboard: pressing ``f`` with no modifiers outside any input focuses
 * the filter input. Esc while focused clears and blurs. Same guard
 * pattern as ``QuickJump`` / ``ExpandCollapseAll``.
 *
 * Counters: when provided, the bar shows "N of M sections" and
 * optionally "…hiding K rows" so operators know whether a blank canvas
 * means "nothing matches" or "I already reviewed these."
 */
export function FilterBar({
  value,
  onChange,
  sectionCounter,
  itemCounter,
  placeholder = "Filter sections + rows (type to narrow)",
  className,
}: {
  value: string;
  onChange: (next: string) => void;
  sectionCounter?: { visible: number; total: number };
  itemCounter?: { hidden: number; total: number };
  placeholder?: string;
  className?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  // ``f`` to focus, same guard as other shortcuts in the app.
  useEffect(() => {
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
      if (e.key === "f") {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const showItemCounter =
    itemCounter !== undefined && value.trim() !== "" && itemCounter.hidden > 0;

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="relative min-w-[200px] max-w-[360px] flex-1">
        <Search
          aria-hidden="true"
          className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-fg"
        />
        <Input
          ref={inputRef}
          type="text"
          value={value}
          placeholder={placeholder}
          aria-label="Filter sections and rows"
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              onChange("");
              inputRef.current?.blur();
            }
          }}
          className="px-8"
        />
        {value !== "" ? (
          <button
            type="button"
            onClick={() => {
              onChange("");
              inputRef.current?.focus();
            }}
            aria-label="Clear filter"
            className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1 text-muted-fg hover:bg-muted hover:text-fg"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        ) : (
          <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2">
            <Kbd>f</Kbd>
          </span>
        )}
      </div>
      {sectionCounter && value.trim() !== "" && (
        <span className="whitespace-nowrap text-xs text-muted-fg">
          {sectionCounter.visible} of {sectionCounter.total} sections
          {showItemCounter &&
            ` · hiding ${itemCounter.hidden} of ${itemCounter.total} rows`}
        </span>
      )}
    </div>
  );
}
