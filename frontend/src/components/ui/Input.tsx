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
        "focus-visible:border-accent focus-visible:outline-none",
        "disabled:opacity-50",
        className,
      )}
      {...rest}
    />
  );
});
