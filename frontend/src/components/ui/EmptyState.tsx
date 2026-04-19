import { type ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * Page-level "nothing here yet" card. Replaces the grab-bag of
 * "No instances yet." one-liners scattered across list pages so
 * the layout doesn't feel abandoned when a fresh install has no
 * data.
 */
export function EmptyState({
  icon,
  headline,
  body,
  cta,
  className,
}: {
  icon?: ReactNode;
  headline: string;
  body?: ReactNode;
  cta?: ReactNode;
  className?: string;
}) {
  return (
    <div
      role="status"
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-lg border border-border",
        "bg-muted/30 px-6 py-10 text-center",
        className,
      )}
    >
      {icon && <div className="text-muted-fg">{icon}</div>}
      <div className="text-sm font-medium text-fg">{headline}</div>
      {body && <div className="max-w-md text-sm text-muted-fg">{body}</div>}
      {cta && <div className="mt-1">{cta}</div>}
    </div>
  );
}
