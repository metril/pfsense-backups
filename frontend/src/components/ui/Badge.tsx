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
        // "warn" uses amber-ish tokens — warmer than muted, less alarm than danger.
        tone === "warn" && "bg-amber-500/15 text-amber-400",
        !tone && "bg-accent/20 text-accent",
        className,
      )}
    >
      {children}
    </span>
  );
}
