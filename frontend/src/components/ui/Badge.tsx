import { cn } from "@/lib/cn";
import type { ReactNode } from "react";

export function Badge({
  tone,
  children,
  className,
  title,
}: {
  tone?: "default" | "success" | "danger" | "muted" | "warn";
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center rounded px-2 py-0.5 text-xs font-medium",
        tone === "success" && "bg-ok/20 text-ok",
        tone === "danger" && "bg-danger/20 text-danger",
        tone === "muted" && "bg-muted text-muted-fg",
        // "warn" uses the palette's warn token (defined in index.css:15)
        // so the amber doesn't diverge from the rest of the theme.
        tone === "warn" && "bg-warn/15 text-warn",
        !tone && "bg-accent/20 text-accent",
        className,
      )}
    >
      {children}
    </span>
  );
}
