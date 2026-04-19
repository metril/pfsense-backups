import { cn } from "@/lib/cn";

/**
 * Loading placeholder with a subtle pulse. Use in the same shape as
 * the row / card being loaded so the layout doesn't jump when real
 * data arrives.
 */
export function Skeleton({
  className,
  ...rest
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden
      className={cn(
        "animate-pulse rounded-md bg-muted/60",
        className,
      )}
      {...rest}
    />
  );
}

/** Convenience: a stack of N table-row-shaped skeletons for lists. */
export function SkeletonRows({ count = 5, className }: { count?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}
