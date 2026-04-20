import { useState } from "react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * Minimal tablist — horizontal buttons that flip a single "active"
 * value. Replaces the ad-hoc TabButton / active-state management in
 * BackupView and BackupDiff.
 *
 * Controlled or uncontrolled. Pass `value` + `onChange` for external
 * control, or omit both for self-managed state seeded with
 * `defaultValue`.
 */
export interface TabItem {
  id: string;
  label: ReactNode;
}

export function Tabs({
  items,
  value,
  defaultValue,
  onChange,
  className,
}: {
  items: TabItem[];
  value?: string;
  defaultValue?: string;
  onChange?: (id: string) => void;
  className?: string;
}) {
  const isControlled = value !== undefined;
  const [internal, setInternal] = useState<string>(
    defaultValue ?? items[0]?.id ?? "",
  );
  const active = isControlled ? value! : internal;
  const set = (id: string) => {
    if (!isControlled) setInternal(id);
    onChange?.(id);
  };
  return (
    <div
      role="tablist"
      className={cn("flex items-center gap-1 border-b border-border", className)}
    >
      {items.map((it) => (
        <button
          key={it.id}
          role="tab"
          aria-selected={active === it.id}
          onClick={() => set(it.id)}
          className={cn(
            "border-b-2 px-3 py-1.5 text-sm transition-colors",
            active === it.id
              ? "border-accent text-accent"
              : "border-transparent text-muted-fg hover:text-fg",
          )}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}
