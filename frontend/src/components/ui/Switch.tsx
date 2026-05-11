import { forwardRef } from "react";
import { cn } from "@/lib/cn";

type Props = {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  id?: string;
  disabled?: boolean;
};

export const Switch = forwardRef<HTMLButtonElement, Props>(function Switch(
  { checked, onChange, label, id, disabled },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      id={id}
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "mt-1 inline-flex h-5 w-9 items-center rounded-full transition-colors",
        checked ? "bg-accent" : "bg-muted",
        disabled && "cursor-not-allowed opacity-50",
      )}
    >
      <span
        className={cn(
          "inline-block h-4 w-4 transform rounded-full bg-fg transition-transform",
          checked ? "translate-x-4" : "translate-x-0.5",
        )}
      />
    </button>
  );
});
