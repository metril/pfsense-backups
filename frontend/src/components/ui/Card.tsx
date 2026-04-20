import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Badge } from "@/components/ui/Badge";
import { groupClasses, type SectionGroup } from "@/lib/sectionGroup";

/**
 * Section Card — the primary container for parsed-config sections.
 *
 * Every section (firewall rules, interfaces, OpenVPN, …) is a Card. The
 * ``group`` prop drives the left-stripe color + title hue so the
 * Security group reads differently from the Services group at a glance.
 * Body uses neutral ``bg-bg`` — we deliberately don't flood-fill: table
 * content needs native contrast to stay legible.
 *
 * The Card is collapsible (click the header to toggle). Default is open.
 */
export function Card({
  title,
  group = "neutral",
  count,
  defaultOpen = true,
  id,
  headerExtra,
  children,
  className,
}: {
  title: string;
  group?: SectionGroup;
  count?: number;
  defaultOpen?: boolean;
  id?: string;
  /** Extra slot rendered on the right side of the header (e.g. diff
   *  badges). Rendered inline with the count. */
  headerExtra?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const gc = groupClasses(group);
  return (
    <section
      id={id}
      className={cn(
        "scroll-anchor rounded border border-border border-l-4 bg-bg",
        gc.stripe,
        className,
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted/40"
      >
        {open ? (
          <ChevronDown aria-hidden="true" className="h-4 w-4 text-muted-fg" />
        ) : (
          <ChevronRight aria-hidden="true" className="h-4 w-4 text-muted-fg" />
        )}
        <span className={cn("text-[15px] font-semibold", gc.title)}>
          {title}
        </span>
        {count !== undefined && (
          <Badge tone="muted" className="font-mono text-[11px]">
            {count}
          </Badge>
        )}
        {headerExtra && <span className="ml-auto flex gap-1">{headerExtra}</span>}
      </button>
      {open && <div className="border-t border-border p-3">{children}</div>}
    </section>
  );
}
