import { AlertCircle, AlertTriangle, CheckCircle2, Info } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export type AlertTone = "info" | "warn" | "danger" | "ok";

const TONE_CLASSES: Record<AlertTone, { border: string; text: string; icon: typeof Info }> = {
  info: { border: "border-info/40 bg-info/10", text: "text-info", icon: Info },
  warn: { border: "border-warn/40 bg-warn/10", text: "text-warn", icon: AlertTriangle },
  danger: { border: "border-danger/40 bg-danger/10", text: "text-danger", icon: AlertCircle },
  ok: { border: "border-ok/40 bg-ok/10", text: "text-ok", icon: CheckCircle2 },
};

/**
 * Inline banner for status messages inside the structured view
 * (expired cert callouts, schema warnings, load errors). Replaces
 * ad-hoc `<div className="p-6 text-sm text-danger">` patterns so
 * errors look the same everywhere.
 */
export function Alert({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: AlertTone;
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  const t = TONE_CLASSES[tone];
  const Icon = t.icon;
  // Errors and warnings need role="alert" (assertive live region) so
  // screen readers interrupt; info/ok stay polite via role="status".
  const role = tone === "danger" || tone === "warn" ? "alert" : "status";
  return (
    <div
      role={role}
      className={cn(
        "flex items-start gap-2 rounded border px-3 py-2 text-sm",
        t.border,
        className,
      )}
    >
      <Icon aria-hidden="true" className={cn("mt-0.5 h-4 w-4 shrink-0", t.text)} />
      <div className="flex-1">
        {title && <div className={cn("font-medium", t.text)}>{title}</div>}
        {children && <div className="text-fg/90">{children}</div>}
      </div>
    </div>
  );
}
