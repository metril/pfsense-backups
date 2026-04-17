import * as RD from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { type ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  className,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <RD.Root open={open} onOpenChange={onOpenChange}>
      <RD.Portal>
        <RD.Overlay className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" />
        <RD.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 w-full max-w-2xl -translate-x-1/2 -translate-y-1/2",
            "rounded-lg border border-border bg-bg p-6 shadow-2xl",
            "max-h-[85vh] overflow-y-auto",
            className,
          )}
        >
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <RD.Title className="text-lg font-semibold">{title}</RD.Title>
              {description && (
                <RD.Description className="mt-1 text-sm text-muted-fg">{description}</RD.Description>
              )}
            </div>
            <RD.Close className="rounded-md p-1 text-muted-fg hover:bg-muted">
              <X className="h-5 w-5" />
            </RD.Close>
          </div>
          {children}
        </RD.Content>
      </RD.Portal>
    </RD.Root>
  );
}
