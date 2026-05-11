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
        // ``transform-gpu`` promotes the track to its own compositing
        // layer so the bg-color transition repaints a tiny isolated
        // surface instead of dirtying the dialog body / shadow.
        "mt-1 inline-flex h-5 w-9 items-center rounded-full transform-gpu transition-colors motion-reduce:transition-none",
        checked ? "bg-accent" : "bg-muted",
        disabled && "cursor-not-allowed opacity-50",
      )}
    >
      <span
        className={cn(
          // ``transform-gpu`` + ``will-change-transform`` keep the thumb
          // on a permanent compositor layer, so the slide is a pure GPU
          // animation with no promote/demote hitch at its boundaries.
          "inline-block h-4 w-4 rounded-full bg-fg transform-gpu will-change-transform transition-transform motion-reduce:transition-none",
          checked ? "translate-x-4" : "translate-x-0.5",
        )}
      />
    </button>
  );
});
