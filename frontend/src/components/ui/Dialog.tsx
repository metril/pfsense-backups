import * as RD from "@radix-ui/react-dialog";
import { AlertOctagon, ShieldAlert, X } from "lucide-react";
import { type ReactNode } from "react";
import { cn } from "@/lib/cn";

type Tone = "default" | "warn" | "danger";

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  tone = "default",
  children,
  className,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  const headerIcon = {
    default: null,
    warn: <ShieldAlert className="h-5 w-5 text-warn" aria-hidden />,
    danger: <AlertOctagon className="h-5 w-5 text-danger" aria-hidden />,
  }[tone];

  // Tone tints only the title block, not the dialog background — a
  // full-card tint overwhelms the dark theme and fights the focused
  // input rings. A thin colored divider under the header is enough to
  // cue "this is destructive" without shouting.
  const headerBorder = {
    default: "border-border",
    warn: "border-warn/40",
    danger: "border-danger/40",
  }[tone];

  const titleColor = {
    default: "text-fg",
    warn: "text-warn",
    danger: "text-danger",
  }[tone];

  return (
    <RD.Root open={open} onOpenChange={onOpenChange}>
      <RD.Portal>
        {/* Plain scrim — no backdrop-filter. A full-viewport
            ``backdrop-blur`` keeps the compositor busy re-evaluating the
            blur every frame, which makes any animation inside the dialog
            (e.g. the toggle switches) drop frames. A slightly darker
            opaque scrim reads the same and costs nothing. */}
        <RD.Overlay className="fixed inset-0 z-40 bg-black/60" />
        <RD.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 w-full max-w-2xl -translate-x-1/2 -translate-y-1/2",
            "rounded-lg border border-border bg-bg p-6 shadow-xl",
            "max-h-[85vh] overflow-y-auto",
            className,
          )}
        >
          <div
            className={cn(
              "mb-4 flex items-start justify-between gap-4 border-b pb-3",
              headerBorder,
            )}
          >
            <div className="flex min-w-0 items-start gap-3">
              {headerIcon && <div className="mt-0.5 shrink-0">{headerIcon}</div>}
              <div className="min-w-0">
                <RD.Title className={cn("text-lg font-semibold", titleColor)}>
                  {title}
                </RD.Title>
                {description && (
                  <RD.Description className="mt-1 text-sm text-muted-fg">
                    {description}
                  </RD.Description>
                )}
              </div>
            </div>
            <RD.Close
              className="rounded-md p-1 text-muted-fg hover:bg-muted"
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </RD.Close>
          </div>
          {children}
        </RD.Content>
      </RD.Portal>
    </RD.Root>
  );
}
