import { forwardRef } from "react";
import { cn } from "@/lib/cn";

type Props = React.InputHTMLAttributes<HTMLInputElement>;

export const Input = forwardRef<HTMLInputElement, Props>(function Input(
  { className, ...rest },
  ref,
) {
  return (
    <input
      ref={ref}
      className={cn(
        "h-9 w-full rounded-md border border-border bg-bg px-3 text-sm",
        "placeholder:text-muted-fg",
        // WCAG 2.4.11 (Focus Appearance) requires a visible focus
        // indicator with ≥2px thickness and 3:1 contrast. The border
        // swap alone was 1px and sub-contrast on dark backgrounds.
        "focus-visible:border-accent focus-visible:outline-none",
        "focus-visible:ring-2 focus-visible:ring-accent/60",
        "disabled:opacity-50",
        className,
      )}
      {...rest}
    />
  );
});
