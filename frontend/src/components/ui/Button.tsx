import { forwardRef } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

const button = cva(
  "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium " +
    "transition-colors focus-visible:outline-none disabled:opacity-50 disabled:pointer-events-none",
  {
    variants: {
      variant: {
        primary: "bg-accent text-accent-fg hover:bg-accent/90",
        secondary: "bg-muted text-fg hover:bg-muted/70 border border-border",
        danger: "bg-danger text-accent-fg hover:bg-danger/90",
        "danger-outline":
          "bg-transparent text-danger border border-danger/40 hover:bg-danger/10",
        ghost: "text-fg hover:bg-muted",
      },
      size: {
        sm: "h-8 px-3",
        md: "h-9 px-4",
        lg: "h-10 px-5",
        icon: "h-9 w-9",
        "icon-sm": "h-7 w-7",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

type Props = React.ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof button>;

export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  { className, variant, size, ...rest },
  ref,
) {
  return <button ref={ref} className={cn(button({ variant, size }), className)} {...rest} />;
});
