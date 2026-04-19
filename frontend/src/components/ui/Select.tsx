import * as RS from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { forwardRef, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export type SelectOption = {
  value: string;
  label: string;
  /** Optional right-aligned secondary text (e.g. timezone offset). */
  hint?: string;
};

type Props = {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  disabled?: boolean;
  "aria-label"?: string;
  "aria-describedby"?: string;
  className?: string;
  /**
   * Renders an extra "__custom__" option at the top of the menu. When
   * the user picks it, ``onChange("__custom__")`` fires so the host
   * component can flip into a free-form text input.
   */
  customOption?: { label: string } | null;
};

/**
 * App-themed dropdown built on Radix Select. Portals its menu so modal
 * overflow clipping can't eat the options, which was the root cause of
 * the "disjointed dropdown" complaint on native <select> elements.
 *
 * Trigger shape matches Input (h-9 rounded-md border-border bg-bg)
 * so Label + Select stacks read exactly like Label + Input.
 */
export const Select = forwardRef<HTMLButtonElement, Props>(function Select(
  {
    value,
    onChange,
    options,
    placeholder,
    disabled,
    className,
    customOption,
    "aria-label": ariaLabel,
    "aria-describedby": ariaDescribedby,
  },
  ref,
) {
  return (
    <RS.Root value={value} onValueChange={onChange} disabled={disabled}>
      <RS.Trigger
        ref={ref}
        aria-label={ariaLabel}
        aria-describedby={ariaDescribedby}
        className={cn(
          "inline-flex h-9 w-full items-center justify-between gap-2 rounded-md",
          "border border-border bg-bg px-3 text-sm",
          "focus-visible:border-accent focus-visible:outline-none",
          "disabled:cursor-not-allowed disabled:opacity-50",
          "data-[placeholder]:text-muted-fg",
          className,
        )}
      >
        <RS.Value placeholder={placeholder} />
        <RS.Icon asChild>
          <ChevronDown className="h-4 w-4 shrink-0 opacity-60" />
        </RS.Icon>
      </RS.Trigger>

      <RS.Portal>
        <RS.Content
          position="popper"
          sideOffset={4}
          collisionPadding={8}
          className={cn(
            "z-[60] min-w-[var(--radix-select-trigger-width)]",
            "max-h-[min(var(--radix-select-content-available-height),320px)]",
            "overflow-hidden rounded-md border border-border bg-muted shadow-2xl",
            // Fade the menu in/out so portaled rendering doesn't pop
            // abruptly over the modal underneath.
            "data-[state=open]:animate-in data-[state=closed]:animate-out",
            "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
          )}
        >
          <RS.Viewport className="max-h-80 overflow-auto p-1">
            {customOption && (
              <Item value="__custom__" label={customOption.label} hint="type your own" />
            )}
            {options.map((o) => (
              <Item key={o.value} value={o.value} label={o.label} hint={o.hint} />
            ))}
          </RS.Viewport>
        </RS.Content>
      </RS.Portal>
    </RS.Root>
  );
});

function Item({
  value,
  label,
  hint,
}: {
  value: string;
  label: string;
  hint?: string;
}) {
  return (
    <RS.Item
      value={value}
      className={cn(
        "relative flex cursor-pointer select-none items-center justify-between gap-3 rounded px-2 py-1.5 text-sm",
        "outline-none data-[highlighted]:bg-accent/15 data-[highlighted]:text-fg",
        "data-[state=checked]:text-fg",
      )}
    >
      <RS.ItemText>{label}</RS.ItemText>
      <span className="flex items-center gap-2">
        {hint && <span className="text-xs text-muted-fg">{hint}</span>}
        <RS.ItemIndicator>
          <Check className="h-3.5 w-3.5 text-accent" />
        </RS.ItemIndicator>
      </span>
    </RS.Item>
  );
}

/** Right-aligned hint text inside a trigger — useful when the trigger
 * should echo more than just the bare label. Currently unused but
 * exported for future use. */
export function SelectHint({ children }: { children: ReactNode }) {
  return <span className="ml-auto text-xs text-muted-fg">{children}</span>;
}
