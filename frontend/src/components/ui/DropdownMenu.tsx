import * as RDM from "@radix-ui/react-dropdown-menu";
import { type ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * App-themed dropdown menu built on Radix DropdownMenu. Portaled so
 * triggers inside modals / narrow containers can open a full-width
 * menu without clipping. Shares visual vocab with Dialog + Select so
 * an open menu next to an open modal doesn't feel like two systems.
 */
export const DropdownMenu = RDM.Root;
export const DropdownMenuTrigger = RDM.Trigger;
export const DropdownMenuPortal = RDM.Portal;

export function DropdownMenuContent({
  children,
  sideOffset = 6,
  align = "end",
  className,
}: {
  children: ReactNode;
  sideOffset?: number;
  align?: "start" | "center" | "end";
  className?: string;
}) {
  return (
    <RDM.Portal>
      <RDM.Content
        sideOffset={sideOffset}
        align={align}
        collisionPadding={8}
        className={cn(
          "z-[60] min-w-44 overflow-hidden rounded-md border border-border",
          "bg-muted p-1 shadow-2xl",
          "data-[state=open]:animate-in data-[state=closed]:animate-out",
          "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
          className,
        )}
      >
        {children}
      </RDM.Content>
    </RDM.Portal>
  );
}

export function DropdownMenuItem({
  children,
  onSelect,
  disabled,
  tone = "default",
  className,
}: {
  children: ReactNode;
  onSelect?: () => void;
  disabled?: boolean;
  tone?: "default" | "danger";
  className?: string;
}) {
  return (
    <RDM.Item
      onSelect={(e) => {
        if (onSelect) {
          e.preventDefault();
          onSelect();
        }
      }}
      disabled={disabled}
      className={cn(
        "flex cursor-pointer select-none items-center gap-2 rounded px-2 py-1.5 text-sm outline-none",
        "data-[highlighted]:bg-accent/15 data-[highlighted]:text-fg",
        "data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50",
        tone === "danger" && "text-danger data-[highlighted]:bg-danger/15",
        className,
      )}
    >
      {children}
    </RDM.Item>
  );
}

export function DropdownMenuSeparator() {
  return <RDM.Separator className="my-1 h-px bg-border" />;
}
