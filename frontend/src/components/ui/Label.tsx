import { cn } from "@/lib/cn";

type Props = React.LabelHTMLAttributes<HTMLLabelElement>;

export function Label({ className, ...rest }: Props) {
  return (
    <label className={cn("text-xs font-medium text-muted-fg", className)} {...rest} />
  );
}
