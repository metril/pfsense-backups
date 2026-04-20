import { useId, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * Horizontal tablist with proper ARIA roles and roving-tabindex keyboard
 * navigation (arrow keys, Home, End). Controlled or uncontrolled via
 * `value` + `onChange` vs `defaultValue`.
 *
 * Emits stable ids for each tab button and (when `panelId` is supplied
 * by the consumer per-item) wires `aria-controls` + `aria-labelledby`
 * so screen readers announce the tab/panel relationship.
 */
export interface TabItem {
  id: string;
  label: ReactNode;
  /** Optional `id` of the panel this tab controls (for aria-controls). */
  panelId?: string;
}

export function Tabs({
  items,
  value,
  defaultValue,
  onChange,
  className,
  ariaLabel,
  idPrefix,
}: {
  items: TabItem[];
  value?: string;
  defaultValue?: string;
  onChange?: (id: string) => void;
  className?: string;
  ariaLabel?: string;
  /** Stable prefix for tab button ids (used by consumers to wire
   * ``aria-labelledby`` on the corresponding panel element). */
  idPrefix?: string;
}) {
  const isControlled = value !== undefined;
  const [internal, setInternal] = useState<string>(
    defaultValue ?? items[0]?.id ?? "",
  );
  const active = isControlled ? value! : internal;
  const generatedId = useId();
  const groupId = idPrefix ?? generatedId;
  const buttonsRef = useRef<Map<string, HTMLButtonElement>>(new Map());

  const set = (id: string) => {
    if (!isControlled) setInternal(id);
    onChange?.(id);
  };

  const focusTab = (id: string) => {
    const el = buttonsRef.current.get(id);
    if (el) el.focus();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const idx = items.findIndex((i) => i.id === active);
    if (idx === -1) return;
    const last = items.length - 1;
    let next = idx;
    if (e.key === "ArrowRight") next = idx === last ? 0 : idx + 1;
    else if (e.key === "ArrowLeft") next = idx === 0 ? last : idx - 1;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = last;
    else return;
    e.preventDefault();
    const nextId = items[next].id;
    set(nextId);
    focusTab(nextId);
  };

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
      className={cn("flex items-center gap-1 border-b border-border", className)}
    >
      {items.map((it) => {
        const selected = active === it.id;
        const tabId = `${groupId}-tab-${it.id}`;
        return (
          <button
            key={it.id}
            id={tabId}
            ref={(el) => {
              if (el) buttonsRef.current.set(it.id, el);
              else buttonsRef.current.delete(it.id);
            }}
            role="tab"
            type="button"
            aria-selected={selected}
            aria-controls={it.panelId}
            tabIndex={selected ? 0 : -1}
            onClick={() => set(it.id)}
            className={cn(
              "border-b-2 px-3 py-1.5 text-sm transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60",
              selected
                ? "border-accent text-accent"
                : "border-transparent text-muted-fg hover:text-fg",
            )}
          >
            {it.label}
          </button>
        );
      })}
    </div>
  );
}
