import { ArrowRight } from "lucide-react";
import { memo, type MouseEvent, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Tooltip } from "@/components/ui/Tooltip";
import { groupClasses } from "@/lib/sectionGroup";
import { useXrefIndex } from "@/components/xref/XrefContext";
import { resolve, scrollAndFlash, xrefHref, type RefKind } from "@/lib/xref";

/**
 * Clickable reference chip. Given a kind + key (e.g. ``kind="interface"``,
 * ``k="lan"``) it resolves the target in the current ``XrefIndex`` and
 * renders a group-colored anchor pointing at the target's DOM id. Click
 * smooth-scrolls + flashes the target; Tab+Enter works without JS.
 *
 * When the target doesn't exist in the index (broken ref, or we render
 * before the index is ready), renders the raw label as plain text —
 * operators still see the value, they just don't get click navigation.
 */
function XrefInner({
  kind,
  k,
  label,
  className,
  fallback,
}: {
  kind: RefKind;
  /** The value stored in the referring field, e.g. ``"lan"`` for an
   *  interface reference or ``"ca_5fa0c4"`` for a CA refid. */
  k: string | null | undefined;
  /** Visible label. Defaults to the target label if the target exists,
   *  else to ``k`` so broken refs still read something. */
  label?: ReactNode;
  className?: string;
  /** Rendered when ``k`` is null / empty / undefined OR when the
   *  target isn't found in the index. Defaults to an em-dash for
   *  null and a muted border chip for unresolved refs. */
  fallback?: ReactNode;
}) {
  const index = useXrefIndex();

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

  const onClick = (e: MouseEvent<HTMLAnchorElement>) => {
    // Keep the anchor semantics (Tab+Enter uses the default) but
    // intercept real clicks so we can smooth-scroll + flash.
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    scrollAndFlash(target.anchorId);
    // Still update the URL hash so copy-link works.
    history.replaceState(null, "", xrefHref(kind, k));
  };

  return (
    <Tooltip content={tooltipContent}>
      <a
        href={xrefHref(kind, k)}
        onClick={onClick}
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

/** Memoized — re-renders only when kind/k change. Chips are rendered
 *  hundreds of times on big configs. */
export const Xref = memo(XrefInner);

/** Convenience for lists: render a comma-free row of chips. */
export function XrefList({
  kind,
  keys,
  className,
}: {
  kind: RefKind;
  keys: string[];
  className?: string;
}) {
  if (keys.length === 0) return <span className="text-muted-fg">—</span>;
  return (
    <span className={cn("inline-flex flex-wrap gap-1", className)}>
      {keys.map((k) => (
        <Xref key={k} kind={kind} k={k} />
      ))}
    </span>
  );
}
