import * as RadixTooltip from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * Lightweight Radix Tooltip wrapper. Keeps the Radix API out of
 * component code (callers never import the primitive directly) and
 * defaults to the small delay + dark surface the rest of the app
 * uses.
 *
 * The Radix Provider lives at app root; callers only render
 * `<Tooltip content="...">...</Tooltip>`.
 */
export function TooltipProvider({ children }: { children: ReactNode }) {
  return (
    <RadixTooltip.Provider delayDuration={250} skipDelayDuration={100}>
      {children}
    </RadixTooltip.Provider>
  );
}

export function Tooltip({
  content,
  side = "top",
  align = "center",
  children,
  className,
}: {
  content: ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  align?: "start" | "center" | "end";
  children: ReactNode;
  className?: string;
}) {
  if (content === null || content === undefined || content === "") {
    return <>{children}</>;
  }
  return (
    <RadixTooltip.Root>
      <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
      <RadixTooltip.Portal>
        <RadixTooltip.Content
          side={side}
          align={align}
          sideOffset={4}
          className={cn(
            "z-50 max-w-xs rounded border border-border bg-bg px-2 py-1",
            "text-xs text-fg shadow-lg",
            "data-[state=delayed-open]:animate-in data-[state=delayed-open]:fade-in-0",
            className,
          )}
        >
          {content}
          <RadixTooltip.Arrow className="fill-border" />
        </RadixTooltip.Content>
      </RadixTooltip.Portal>
    </RadixTooltip.Root>
  );
}
