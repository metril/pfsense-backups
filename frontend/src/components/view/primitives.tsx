/**
 * Shared rendering primitives for ``ParsedBackupView`` and its
 * extracted panel files under ``view/``.
 *
 * These used to live inline at the top of ``ParsedBackupView.tsx``
 * before the v0.19.0 directory split — extracting them here lets
 * per-section files import the building blocks without recreating
 * the behaviour.
 *
 * Everything in this module is presentation-only and stateless; no
 * provider wiring, no xref lookups.
 */

import { Lock } from "lucide-react";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui/Badge";

/** Two-column definition list. ``items`` is a tuple of
 *  ``[label, value]`` or ``[label, value, fieldId]``. When a third
 *  element is supplied it's applied as ``id`` on the ``<dt>`` so
 *  the Structured ↔ Raw XML tab-switch sync (v0.22.0) can track
 *  which row is in view via IntersectionObserver. Non-id-bearing
 *  rows (Badge toolbars, meta rows without a field mapping) stay
 *  anonymous. */
export type DlRow =
  | [string, ReactNode]
  | [string, ReactNode, string | undefined];

export function Dl({ items }: { items: DlRow[] }) {
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
      {items.map((row) => {
        const [k, v, id] = row;
        return (
          <div key={k} className="contents">
            <dt id={id} className="text-muted-fg">
              {k}
            </dt>
            <dd className="font-mono">{v}</dd>
          </div>
        );
      })}
    </dl>
  );
}

/** Lock-glyph chip used wherever the parser replaced a secret value
 *  with the ``***redacted***`` placeholder. Hover tooltip points
 *  operators at the raw-XML fallback if they truly need the
 *  plaintext (which they almost never do — the parsed view is the
 *  safe default). */
export function Redacted() {
  return (
    <span
      title="Value redacted server-side — view raw XML tab if you truly need the plaintext"
      className="inline-flex items-center gap-1 rounded border border-[hsl(var(--group-vpn))]/30 bg-[hsl(var(--group-vpn))]/10 px-1.5 py-0.5 font-mono text-[11px] text-[hsl(var(--group-vpn))]"
    >
      <Lock aria-hidden="true" className="h-3 w-3" /> redacted
    </span>
  );
}

/** Redact-aware value: ``"***redacted***"`` → ``<Redacted />``; null /
 *  undefined / empty → em-dash; anything else → passthrough. */
export function RV({ v }: { v: string | null | undefined }) {
  if (v === "***redacted***") return <Redacted />;
  return <>{v || <span className="text-muted-fg">—</span>}</>;
}

/** Basic table with optional per-row keys and DOM ids. Used by every
 *  tabular section in the viewer. */
export function Table({
  headers,
  rows,
  rowKeys,
  rowIds,
}: {
  headers: string[];
  rows: ReactNode[][];
  /** Stable per-row keys. When omitted, falls back to index which is
   *  fine for non-reordering tables. Firewall / NAT tables pass
   *  rule trackers so reordering diffs don't confuse React. */
  rowKeys?: (string | number)[];
  /** Per-row DOM ``id``s. Used to make table rows xref targets so
   *  ``<Xref>`` chips can scroll into them. Typically produced by
   *  ``itemId(kind, key)`` from ``@/lib/xref``. */
  rowIds?: (string | undefined)[];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-border text-xs uppercase text-muted-fg">
            {headers.map((h) => (
              <th key={h} className="px-2 py-1 font-normal">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={rowKeys?.[i] ?? i}
              id={rowIds?.[i]}
              className="border-b border-border/50 last:border-0"
            >
              {row.map((cell, j) => (
                <td key={j} className="px-2 py-1 align-top">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Muted-border wrapper for each installed-package panel. Used by
 *  ``PackagesPanel`` children (pfBlockerNG, HAProxy, Suricata, …). */
export function PackageCard({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded border border-border/70 bg-muted/20 p-2">
      <div className="mb-1 text-sm font-medium">{title}</div>
      {children}
    </div>
  );
}

/** Colored badge for firewall rule actions. "pass"/"allow" → success
 *  (green), "block"/"reject" → danger (red), "match" → warn (amber),
 *  anything else → muted. */
export function ActionPill({
  type,
}: {
  type: string | null | undefined;
}) {
  if (!type) return <span className="text-muted-fg">—</span>;
  const t = type.toLowerCase();
  let tone: "success" | "danger" | "warn" | "muted" = "muted";
  if (t === "pass" || t === "allow") tone = "success";
  else if (t === "block" || t === "reject") tone = "danger";
  else if (t === "match") tone = "warn";
  return (
    <Badge tone={tone} className="uppercase">
      {type}
    </Badge>
  );
}

/** On/off badge. ``enabled`` drives color; ``labels`` overrides the
 *  default ``"enabled"`` / ``"disabled"`` text for contexts where
 *  different words read better (e.g. ``{on: "yes", off: "no"}`` on
 *  boolean toggles). */
export function StatusPill({
  enabled,
  labels,
}: {
  enabled: boolean;
  labels?: { on: string; off: string };
}) {
  const on = labels?.on ?? "enabled";
  const off = labels?.off ?? "disabled";
  return (
    <Badge tone={enabled ? "success" : "muted"}>
      {enabled ? on : off}
    </Badge>
  );
}
