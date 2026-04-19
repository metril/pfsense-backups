import { ChevronDown } from "lucide-react";
import { type ReactNode } from "react";
import { cn } from "@/lib/cn";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./DropdownMenu";

type Variant = "primary" | "secondary";
type Size = "md" | "sm";

/**
 * Primary action + overflow menu paired into one control.
 *
 * Layout: ``[icon? label │ ▾]`` — the main region triggers the
 * default action; the chevron region opens a dropdown with
 * "with options…" entries. Replaces the separate "play + gear"
 * button pairs that operators couldn't parse.
 *
 * Keyboard: Tab focuses the primary first, then the chevron. Alt+↓
 * on either opens the menu (via Radix DropdownMenu).
 */
export function SplitButton({
  primaryLabel,
  primaryIcon,
  primaryAriaLabel,
  onPrimary,
  disabled,
  variant = "primary",
  size = "md",
  menu,
  menuAriaLabel,
  className,
  compact = false,
}: {
  primaryLabel?: string;
  primaryIcon?: ReactNode;
  /** Required when ``compact`` is true — the primary is icon-only. */
  primaryAriaLabel?: string;
  onPrimary: () => void;
  disabled?: boolean;
  variant?: Variant;
  size?: Size;
  menu: Array<{
    label: string;
    onSelect: () => void;
    disabled?: boolean;
    tone?: "default" | "danger";
  }>;
  menuAriaLabel?: string;
  className?: string;
  /** Icon-only primary with a tight chevron — for table-row density. */
  compact?: boolean;
}) {
  const base = cn(
    "inline-flex items-center gap-2 text-sm font-medium transition-colors",
    "focus-visible:outline-none disabled:opacity-50 disabled:pointer-events-none",
  );
  const variantClass = {
    primary: "bg-accent text-accent-fg hover:bg-accent/90",
    secondary: "bg-muted text-fg border border-border hover:bg-muted/70",
  }[variant];

  // Primary-region shape: no right border radius (the chevron is the
  // right cap). The inner divider line sits between the two regions.
  const primaryShape = compact
    ? "h-7 w-7 justify-center rounded-l-md"
    : size === "sm"
    ? "h-8 pl-3 pr-2.5 rounded-l-md"
    : "h-9 pl-4 pr-3 rounded-l-md";

  const chevronShape = compact
    ? "h-7 w-6 justify-center rounded-r-md"
    : size === "sm"
    ? "h-8 w-7 justify-center rounded-r-md"
    : "h-9 w-8 justify-center rounded-r-md";

  // A 1px inner divider between the two regions. We do it via a
  // pseudo-element-like classname rather than a separate <div> so
  // the two <button>s stay flush without flex-gap artifacts.
  const divider =
    variant === "primary"
      ? "border-l border-accent-fg/20"
      : "border-l border-border";

  return (
    <div className={cn("inline-flex", className)}>
      <button
        type="button"
        onClick={onPrimary}
        disabled={disabled}
        aria-label={compact ? primaryAriaLabel : undefined}
        className={cn(base, variantClass, primaryShape)}
      >
        {primaryIcon}
        {!compact && primaryLabel}
      </button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            disabled={disabled}
            aria-label={menuAriaLabel ?? `${primaryLabel ?? primaryAriaLabel} options`}
            className={cn(base, variantClass, chevronShape, divider)}
          >
            <ChevronDown className={compact ? "h-3.5 w-3.5" : "h-4 w-4"} />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          {menu.map((item) => (
            <DropdownMenuItem
              key={item.label}
              onSelect={item.onSelect}
              disabled={item.disabled}
              tone={item.tone}
            >
              {item.label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
