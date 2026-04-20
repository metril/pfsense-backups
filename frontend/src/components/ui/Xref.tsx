import { ArrowRight } from "lucide-react";
import { memo, type MouseEvent, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Tooltip } from "@/components/ui/Tooltip";
import { groupClasses } from "@/lib/sectionGroup";
import {
  useXrefEntry,
  type XrefSide,
} from "@/components/xref/XrefContext";
import {
  expandThenScrollToHash,
  resolve,
  xrefHref,
  type RefKind,
} from "@/lib/xref";

/**
 * Clickable reference chip. Given a kind + key (e.g. ``kind="interface"``,
 * ``k="lan"``) it resolves the target in the current ``XrefIndex`` and
 * renders a group-colored anchor pointing at the target.
 *
 * Two behaviors, picked by the provider's ``hrefMode``:
 * - **hash** (viewer): anchor href is ``#xref-{kind}-{key}``; click
 *   smooth-scrolls, auto-expands the containing card, and flashes.
 * - **route** (diff): anchor href is ``/backups/{backupId}/view#xref-…``;
 *   opens in a new tab so the diff context stays put.
 *
 * When the target doesn't exist in the index (broken ref, or we render
 * before the index is ready), renders the raw label as plain text —
 * operators still see the value, they just don't get click navigation.
 */
function XrefInner({
  kind,
  k,
  side,
  label,
  className,
  fallback,
}: {
  kind: RefKind;
  /** The value stored in the referring field, e.g. ``"lan"`` for an
   *  interface reference or ``"ca_5fa0c4"`` for a CA refid. */
  k: string | null | undefined;
  /** Which provider to resolve against when two are stacked (diff
   *  view). Unset on viewer pages — falls back to nearest provider. */
  side?: XrefSide;
  /** Visible label. Defaults to the target label if the target exists,
   *  else to ``k`` so broken refs still read something. */
  label?: ReactNode;
  className?: string;
  /** Rendered when ``k`` is null / empty / undefined OR when the
   *  target isn't found in the index. Defaults to an em-dash for
   *  null and a muted border chip for unresolved refs. */
  fallback?: ReactNode;
}) {
  const entry = useXrefEntry(side);
  const index = entry?.index ?? null;

  if (!k) {
    return (
      fallback !== undefined
        ? <>{fallback}</>
        : <span className="text-muted-fg">—</span>
    );
  }

  const target = index ? resolve(index, kind, k) : null;
  const visibleLabel = label ?? target?.label ?? k;

  if (!target) {
    // Broken or out-of-index ref: let the caller render its preferred
    // visual (e.g. the InterfaceChip fall back to its hash-colored
    // span so interfaces referenced-but-not-indexed still look like
    // interfaces). Otherwise render a muted border chip.
    if (fallback !== undefined) return <>{fallback}</>;
    return (
      <span
        className={cn(
          "inline-flex items-center rounded border border-border/50 px-1.5 py-0.5 text-[11px] font-medium text-muted-fg",
          className,
        )}
        title={`Unresolved ${kind} reference`}
      >
        {visibleLabel}
      </span>
    );
  }

  const gc = groupClasses(target.group);
  const incoming = index?.incoming.get(target.anchorId)?.length ?? 0;
  const tooltipContent = (
    <div className="flex flex-col gap-0.5">
      <div className="font-medium">{target.label}</div>
      <div className="text-muted-fg">
        {kind.replace(/_/g, " ")}
        {target.secondary ? ` — ${target.secondary}` : ""}
      </div>
      {incoming > 1 && (
        <div className="text-muted-fg">Used by {incoming} items</div>
      )}
    </div>
  );

  const hrefMode = entry?.hrefMode ?? "hash";
  const href =
    hrefMode === "route" && entry?.backupId != null
      ? `/backups/${entry.backupId}/view${xrefHref(kind, k)}`
      : xrefHref(kind, k);

  const onClick = (e: MouseEvent<HTMLAnchorElement>) => {
    // Let modifier-clicks fall through to the browser (new tab, window, etc).
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    if (hrefMode === "route") {
      // Natural navigation (opens in new tab via target="_blank" below).
      return;
    }
    e.preventDefault();
    expandThenScrollToHash(xrefHref(kind, k));
  };

  return (
    <Tooltip content={tooltipContent}>
      <a
        href={href}
        onClick={onClick}
        {...(hrefMode === "route"
          ? { target: "_blank", rel: "noopener noreferrer" }
          : {})}
        className={cn(
          "inline-flex items-center gap-0.5 rounded border bg-bg px-1.5 py-0.5 text-[11px] font-medium",
          "transition-colors hover:bg-muted/40",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60",
          gc.title,
          gc.chipBorder,
          className,
        )}
      >
        <span>{visibleLabel}</span>
        <ArrowRight aria-hidden="true" className="h-3 w-3 opacity-60" />
      </a>
    </Tooltip>
  );
}

/** Memoized — re-renders only when kind/k/side change. Chips are
 *  rendered hundreds of times on big configs. */
export const Xref = memo(XrefInner);

/** Convenience for lists: render a comma-free row of chips. */
export function XrefList({
  kind,
  keys,
  side,
  className,
}: {
  kind: RefKind;
  keys: string[];
  side?: XrefSide;
  className?: string;
}) {
  if (keys.length === 0) return <span className="text-muted-fg">—</span>;
  return (
    <span className={cn("inline-flex flex-wrap gap-1", className)}>
      {keys.map((k) => (
        <Xref key={k} kind={kind} k={k} side={side} />
      ))}
    </span>
  );
}
