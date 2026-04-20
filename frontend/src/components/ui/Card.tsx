import { ChevronDown, ChevronRight } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Badge } from "@/components/ui/Badge";
import { groupClasses, type SectionGroup } from "@/lib/sectionGroup";
import { useCardGroup } from "@/components/CardGroupContext";

/**
 * Section Card — the primary container for parsed-config sections.
 *
 * Every section (firewall rules, interfaces, OpenVPN, …) is a Card. The
 * ``group`` prop drives the left-stripe color + title hue so the
 * Security group reads differently from the Services group at a glance.
 * Body uses neutral ``bg-bg`` — we deliberately don't flood-fill: table
 * content needs native contrast to stay legible.
 *
 * Collapsible (click the header to toggle). Default is open. When
 * rendered inside a ``<CardGroupProvider>`` the card also:
 *   - snaps to the provider's ``snapTo`` state whenever the provider's
 *     ``resetVersion`` ticks (expand-all / collapse-all); and
 *   - persists its own open/closed state under ``cardState:{scope}:{id}``
 *     in ``sessionStorage`` so navigating away + back preserves
 *     per-card layout.
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
  const groupCtx = useCardGroup();
  const storageKey =
    groupCtx?.scope && id ? `cardState:${groupCtx.scope}:${id}` : null;

  // Seed from sessionStorage if the key is present, else fall back to
  // ``defaultOpen``. The read happens once in the initializer so we
  // don't flicker open → closed on mount.
  const [open, setOpen] = useState<boolean>(() => {
    if (storageKey) {
      try {
        const persisted = sessionStorage.getItem(storageKey);
        if (persisted === "open") return true;
        if (persisted === "closed") return false;
      } catch {
        // sessionStorage unavailable (private mode, SSR, etc.) — fall through.
      }
    }
    return defaultOpen;
  });

  // Broadcast: when the provider's resetVersion ticks, snap to the new
  // ``snapTo`` state. Skip the initial mount so the seed above is
  // respected.
  const initialMountRef = useRef(true);
  useEffect(() => {
    if (!groupCtx) return;
    if (initialMountRef.current) {
      initialMountRef.current = false;
      return;
    }
    setOpen(groupCtx.snapTo);
    if (storageKey) {
      try {
        sessionStorage.setItem(
          storageKey,
          groupCtx.snapTo ? "open" : "closed",
        );
      } catch {
        // ignore
      }
    }
    // Only snap when resetVersion ticks. Deliberately omitting snapTo
    // from deps — we only want to react to a fresh broadcast, not a
    // mid-mount context value change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupCtx?.resetVersion]);

  // Targeted open: deep-link handler calls snapTarget(cardId); if this
  // Card's id matches, force-open. No-op if already open; persists so
  // the reopen sticks across navigations.
  useEffect(() => {
    if (!groupCtx) return;
    if (!id) return;
    if (groupCtx.snapTargetId !== id) return;
    setOpen(true);
    if (storageKey) {
      try {
        sessionStorage.setItem(storageKey, "open");
      } catch {
        // ignore
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupCtx?.snapTargetVersion]);

  const persistToggle = (next: boolean) => {
    setOpen(next);
    if (storageKey) {
      try {
        sessionStorage.setItem(storageKey, next ? "open" : "closed");
      } catch {
        // ignore
      }
    }
  };

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
        onClick={() => persistToggle(!open)}
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
