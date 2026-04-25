import type { ReactNode } from "react";
import { ArrowLeft, type LucideIcon } from "lucide-react";
import { Kbd } from "@/components/ui/Kbd";
import { cn } from "@/lib/cn";

/**
 * Floating accent-outlined pill, shared between the within-backup
 * cross-reference back-stack (``XrefBackPill``) and the cross-backup
 * "return to originating backup" pill (``ReturnToBackupPill``).
 *
 * Both pills share the same visual signature so operators learn one
 * affordance; only the ``position`` differs (left = cross-backup /
 * broader return, right = within-backup / narrower return).
 *
 * The pill is always rendered when visible — there's no hide-when-
 * empty toggle. Callers guard on their own state (e.g. stack depth,
 * presence of ``?from=``) before rendering.
 */
export function BackPill({
  icon: Icon = ArrowLeft,
  label,
  kbd,
  onClick,
  position = "right",
  trailing,
  ariaLabel,
  title,
}: {
  /** Icon component; defaults to ``ArrowLeft``. Accepts any
   *  ``LucideIcon`` — the lucide prop type permits ``Booleanish``
   *  (string-ish boolean) which plain ``ComponentType<{aria-hidden: boolean}>``
   *  rejects, so we lean on lucide's own exported type. */
  icon?: LucideIcon;
  /** Main label text. Can include ``<span>`` children for emphasis. */
  label: ReactNode;
  /** Keyboard shortcut hint rendered via ``<Kbd>``; e.g. ``"["`` or ``"]"``. */
  kbd?: string;
  onClick: () => void;
  /** Which bottom corner to pin to. */
  position?: "left" | "right";
  /** Optional trailing content (stack-depth badge, notification dot, …). */
  trailing?: ReactNode;
  ariaLabel?: string;
  title?: string;
}) {
  return (
    // v0.41.18: ``position="left"`` previously pinned to ``left-4``
    // which put the pill directly on top of the 14rem-wide sidebar's
    // Sign-out / user-email row at the bottom of Layout.tsx. Bumped
    // to ``left-60`` (15rem = sidebar width 14rem + 1rem gap) so the
    // pill lives in the main content column where it belongs.
    <div
      className={cn(
        "pointer-events-none fixed bottom-4 z-40 flex",
        position === "right" ? "right-4 justify-end" : "left-60 justify-start",
      )}
    >
      <button
        type="button"
        onClick={onClick}
        aria-label={ariaLabel}
        title={title}
        className={cn(
          "pointer-events-auto inline-flex items-center gap-1.5 rounded-full",
          "border-2 border-accent bg-bg px-3 py-1.5 text-sm font-medium text-accent shadow-lg",
          "transition-colors hover:bg-accent hover:text-accent-fg",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60",
        )}
      >
        <Icon aria-hidden className="h-4 w-4" />
        <span>{label}</span>
        {kbd && <Kbd className="ml-1">{kbd}</Kbd>}
        {trailing}
      </button>
    </div>
  );
}
