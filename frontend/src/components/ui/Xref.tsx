import { ArrowRight } from "lucide-react";
import { memo, type MouseEvent, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Tooltip } from "@/components/ui/Tooltip";
import { groupClasses } from "@/lib/sectionGroup";
import {
  useXrefEntry,
  type XrefSide,
} from "@/components/xref/XrefContext";
import { useXrefHistory } from "@/components/xref/XrefHistory";
import {
  expandThenScrollToHash,
  findOriginLabel,
  findTargetByAnchorId,
  resolve,
  xrefHref,
  type RefKind,
  type XrefIndex,
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

/** Walk up from the clicked chip to find the id of the row / item
 *  the chip sits inside — that's the "origin" we record on the back
 *  stack so the operator can rewind. Skips any wrapping element that
 *  isn't itself a proper xref anchor id (``xref-*``). */
function findOriginAnchorId(from: HTMLElement): string | null {
  let cur: HTMLElement | null = from.parentElement;
  while (cur) {
    if (cur.id && cur.id.startsWith("xref-")) return cur.id;
    cur = cur.parentElement;
  }
  return null;
}

/** Derive a short human label for a back-stack entry. Uses the xref
 *  index first (proper targets have a ``label`` field); falls back to
 *  parsing the id for leaf rows like firewall rules / NAT rules that
 *  are anchored via ``rowAnchorId("rule", tracker)``. */
function labelForOrigin(
  index: XrefIndex | null,
  originId: string,
): string {
  if (index) {
    const target = findTargetByAnchorId(index, originId);
    if (target) return `${target.kind.replace(/_/g, " ")}: ${target.label}`;
    // Leaf rows (firewall rules, NATs) aren't proper xref targets —
    // their descriptions are recorded separately in
    // ``index.originLabels`` at build time so we can surface a
    // readable row label instead of the opaque tracker key.
    const origin = findOriginLabel(index, originId);
    if (origin) {
      const scope = /^xref-([^-]+)-/.exec(originId)?.[1] ?? "row";
      return `${scope.replace(/_/g, " ")}: ${origin}`;
    }
  }
  // Ultimate fallback: parse the id and show ``rule: tracker_…``.
  const m = /^xref-([^-]+)-(.+)$/.exec(originId);
  if (m) return `${m[1].replace(/_/g, " ")}: ${m[2]}`;
  return "previous location";
}
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
  const history = useXrefHistory();

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
      {incoming > 0 && (
        <div className="text-muted-fg">
          Used by {incoming} {incoming === 1 ? "item" : "items"}
        </div>
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
    // Capture the origin row BEFORE navigating — the chip we clicked
    // is inside some row / item, and that's where the operator will
    // want to return. ``history`` is ``null`` when no provider is
    // mounted (diff view), so we silently skip push there.
    if (history) {
      const originId = findOriginAnchorId(e.currentTarget);
      if (originId && originId !== target.anchorId) {
        history.push({
          anchorId: originId,
          label: labelForOrigin(index, originId),
        });
      }
    }
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

/** Memoized to skip re-renders caused by sibling / parent state
 *  changes — kind/k/side prop stability + memo avoids thrashing the
 *  hundreds of chips a big config produces. Note: any change to the
 *  ``XrefContext`` value (stacked providers mounting, a fresh config
 *  arriving) still re-renders every chip because ``useXrefEntry``
 *  reads from context. In practice that's a one-time cost per data
 *  arrival, not a per-keystroke cost. */
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
