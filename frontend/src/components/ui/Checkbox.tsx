import { forwardRef } from "react";
import { cn } from "@/lib/cn";

type Props = {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  id?: string;
  disabled?: boolean;
  className?: string;
};

export const Checkbox = forwardRef<HTMLInputElement, Props>(function Checkbox(
  { checked, onChange, label, id, disabled, className },
  ref,
) {
  return (
    <label className={cn("flex cursor-pointer items-center gap-2 text-sm", className)}>
      <input
        ref={ref}
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 cursor-pointer accent-accent"
      />
      <span>{label}</span>
    </label>
  );
});
