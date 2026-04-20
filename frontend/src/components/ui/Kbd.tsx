import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * Styled keyboard-shortcut hint, e.g. ``<Kbd>/</Kbd>`` or
 * ``<Kbd>Esc</Kbd>``. Used in the QuickJump palette hint and inline
 * help text; not interactive.
 */
export function Kbd({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <kbd
      className={cn(
        "inline-flex min-w-[1.25rem] items-center justify-center rounded border border-border bg-muted/50 px-1 py-0.5 font-mono text-[10px] text-muted-fg",
        "shadow-[inset_0_-1px_0_rgba(0,0,0,0.2)]",
        className,
      )}
    >
      {children}
    </kbd>
  );
}
