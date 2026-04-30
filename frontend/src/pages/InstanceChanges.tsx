/**
 * Cumulative-changes page (v0.40.0).
 *
 * Lists every anchor on the selected instance that has ≥1 event in
 * a backup-range window, collapsed to "original → current" — sorted
 * by most recently changed. Answers the question "what on this
 * pfSense is different from when I first backed it up?" in one
 * screen.
 *
 * Data comes from ``/cumulative-changes`` which rides the
 * ``anchor_event`` table. Per-row drill-in opens the existing
 * ``AnchorHistoryDrawer`` for that anchor.
 */

import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ChevronDown, ChevronUp, Clock, History } from "lucide-react";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import {
  useBackups,
  useCumulativeChanges,
  useInstances,
  type CumulativeChangeRow,
} from "@/api/queries";
import { AnchorHistoryDrawer } from "@/components/xref/AnchorHistoryDrawer";
import { formatLocal } from "@/lib/datetime";
import { formatRelative } from "@/lib/formatRelative";

// Radix Select refuses empty-string values (v1.x emits a console
// warning + fails to call onValueChange). Use explicit sentinels for
// each "any/first/latest" option and translate back to ``null``
// before passing to the TanStack query.
const SENTINEL_ALL = "__all__";
const SENTINEL_FIRST = "__first__";
const SENTINEL_LATEST = "__latest__";

function kindTone(kind: CumulativeChangeRow["latest_kind"]) {
  switch (kind) {
    case "added":
      return "success";
    case "modified":
      return "warn";
    case "removed":
      return "danger";
    case "reordered":
      return "muted";
  }
}

function ValueBlock({
  value,
  label,
}: {
  value: unknown;
  label: string;
}) {
  const display = useMemo(() => {
    if (value == null) return "—";
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      return String(value);
    }
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }, [value]);
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <div className="text-[10px] uppercase text-muted-fg">{label}</div>
      <pre className="max-h-40 overflow-auto rounded border border-border/70 bg-muted/30 p-2 text-xs font-mono whitespace-pre-wrap break-all">
        {display}
      </pre>
    </div>
  );
}

export function InstanceChangesPage() {
  const { id: idParam } = useParams();
  const instanceId = Number(idParam);

  const instances = useInstances();
  const instance = instances.data?.find((i) => i.id === instanceId);

  // Ascending backup list for the range picker.
  const backupsQuery = useBackups({
    instanceId,
    sort: "started_at",
    order: "asc",
  });
  const backups = useMemo(
    () => (backupsQuery.data ?? []).filter((b) => b.success),
    [backupsQuery.data],
  );

  const [sinceId, setSinceId] = useState<string>(SENTINEL_FIRST);
  const [untilId, setUntilId] = useState<string>(SENTINEL_LATEST);
  const sinceBackupId =
    sinceId === SENTINEL_FIRST || !sinceId ? null : Number(sinceId);
  const untilBackupId =
    untilId === SENTINEL_LATEST || !untilId ? null : Number(untilId);

  const cumulative = useCumulativeChanges(
    instanceId,
    sinceBackupId,
    untilBackupId,
  );

  // Client-side filters. Selects use the SENTINEL_ALL sentinel
  // rather than empty string per Radix requirements.
  const [sectionFilter, setSectionFilter] = useState<string>(SENTINEL_ALL);
  const [kindFilter, setKindFilter] = useState<string>(SENTINEL_ALL);
  const [textFilter, setTextFilter] = useState<string>("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [openAnchor, setOpenAnchor] = useState<string | null>(null);

  const rows = useMemo(
    () => cumulative.data?.rows ?? [],
    [cumulative.data],
  );
  const filteredRows = useMemo(() => {
    let out = rows;
    if (sectionFilter !== SENTINEL_ALL)
      out = out.filter((r) => r.section === sectionFilter);
    if (kindFilter !== SENTINEL_ALL)
      out = out.filter((r) => r.latest_kind === kindFilter);
    if (textFilter) {
      const q = textFilter.toLowerCase();
      out = out.filter(
        (r) =>
          r.label.toLowerCase().includes(q) ||
          r.anchor_id.toLowerCase().includes(q),
      );
    }
    return out;
  }, [rows, sectionFilter, kindFilter, textFilter]);

  const sections = useMemo(() => {
    const s = new Set<string>();
    for (const r of rows) {
      if (r.section) s.add(r.section);
    }
    return Array.from(s).sort();
  }, [rows]);

  const backupOptions = useMemo(
    () =>
      backups.map((b) => ({
        value: String(b.id),
        label: formatLocal(b.started_at),
        hint: b.tag ?? undefined,
      })),
    [backups],
  );

  if (!instance && !instances.isLoading) {
    return (
      <div className="p-6">
        <Alert tone="danger" title="Instance not found" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <Link
            to={`/instances/${instanceId}/history`}
            className="inline-flex items-center gap-1 text-sm text-muted-fg hover:text-fg"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>History</span>
          </Link>
          <div className="min-w-0">
            <div className="truncate text-base font-medium">
              Changes · {instance?.name ?? `id=${instanceId}`}
            </div>
            <div className="text-xs text-muted-fg">
              Everything different since the first backup (or the
              window you pick). Click a row for full blame history.
            </div>
          </div>
        </div>
      </div>

      {/* Range + filters. ``htmlFor`` omitted on the Select controls
          because Radix Select's trigger is a portaled button with no
          stable id — the label associations rely on ``aria-label``
          on each Select instead. */}
      <div className="flex flex-wrap items-end gap-3 border-b border-border px-4 py-3">
        <div className="flex min-w-[220px] flex-col gap-1">
          <span className="text-xs uppercase text-muted-fg">Since</span>
          <Select
            value={sinceId}
            onChange={setSinceId}
            options={[
              { value: SENTINEL_FIRST, label: "First retained backup" },
              ...backupOptions,
            ]}
            aria-label="Since backup"
          />
        </div>
        <div className="flex min-w-[220px] flex-col gap-1">
          <span className="text-xs uppercase text-muted-fg">Until</span>
          <Select
            value={untilId}
            onChange={setUntilId}
            options={[
              { value: SENTINEL_LATEST, label: "Latest backup" },
              ...backupOptions,
            ]}
            aria-label="Until backup"
          />
        </div>
        <div className="flex min-w-[180px] flex-col gap-1">
          <span className="text-xs uppercase text-muted-fg">Section</span>
          <Select
            value={sectionFilter}
            onChange={setSectionFilter}
            options={[
              { value: SENTINEL_ALL, label: "All sections" },
              ...sections.map((s) => ({ value: s, label: s })),
            ]}
            aria-label="Filter by section"
          />
        </div>
        <div className="flex min-w-[140px] flex-col gap-1">
          <span className="text-xs uppercase text-muted-fg">Kind</span>
          <Select
            value={kindFilter}
            onChange={setKindFilter}
            options={[
              { value: SENTINEL_ALL, label: "Any kind" },
              { value: "added", label: "added" },
              { value: "modified", label: "modified" },
              { value: "removed", label: "removed" },
              { value: "reordered", label: "reordered" },
            ]}
            aria-label="Filter by kind"
          />
        </div>
        <div className="flex flex-1 min-w-[220px] flex-col gap-1">
          <label className="text-xs uppercase text-muted-fg" htmlFor="filter">
            Filter
          </label>
          <Input
            id="filter"
            type="text"
            placeholder="Search label or anchor id…"
            value={textFilter}
            onChange={(e) => setTextFilter(e.target.value)}
          />
        </div>
      </div>

      {/* Status strip */}
      <div className="flex items-center gap-3 border-b border-border/60 px-4 py-2 text-xs text-muted-fg">
        {cumulative.isLoading && <span>Loading changes…</span>}
        {cumulative.isError && (
          <Alert tone="danger" title="Failed to load changes">
            {String(cumulative.error)}
          </Alert>
        )}
        {cumulative.data && !cumulative.data.indexed && (
          <Alert tone="warn" title="Index not ready">
            This instance hasn't been backfilled yet. Run{" "}
            <code>python -m worker reindex-anchor-events --instance={instanceId}</code>
            {" "}on the worker, or wait for the next backup to seed the
            index.
          </Alert>
        )}
        {cumulative.data && cumulative.data.indexed && (
          <span>
            {filteredRows.length} of {rows.length} changed rows
            {sectionFilter !== SENTINEL_ALL ||
            kindFilter !== SENTINEL_ALL ||
            textFilter
              ? " (filtered)"
              : ""}
          </span>
        )}
      </div>

      {/* Rows */}
      <div className="flex-1 overflow-auto p-3">
        {cumulative.data?.indexed && rows.length === 0 && (
          <div className="p-6 text-sm text-muted-fg">
            No changes in this window. Try widening the backup range.
          </div>
        )}
        <ul className="grid gap-2">
          {filteredRows.map((row) => {
            const isOpen = !!expanded[row.anchor_id];
            return (
              <li
                key={row.anchor_id}
                className="rounded border border-border/70 bg-muted/20"
              >
                <button
                  type="button"
                  onClick={() =>
                    setExpanded((prev) => ({
                      ...prev,
                      [row.anchor_id]: !prev[row.anchor_id],
                    }))
                  }
                  className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted/40"
                >
                  {row.section && (
                    <Badge tone="muted" className="shrink-0">
                      {row.section}
                    </Badge>
                  )}
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">
                    {row.label}
                  </span>
                  <Badge tone={kindTone(row.latest_kind)} className="shrink-0">
                    {row.latest_kind}
                  </Badge>
                  <span className="shrink-0 text-xs text-muted-fg tabular-nums">
                    {row.change_count}×
                  </span>
                  <span className="shrink-0 flex items-center gap-1 text-xs text-muted-fg">
                    <Clock className="h-3 w-3" />
                    {formatRelative(row.last_change_at)}
                  </span>
                  {isOpen ? (
                    <ChevronUp className="h-4 w-4 shrink-0 text-muted-fg" />
                  ) : (
                    <ChevronDown className="h-4 w-4 shrink-0 text-muted-fg" />
                  )}
                </button>
                {isOpen && (
                  <div className="border-t border-border/60 px-3 py-2">
                    <div className="mb-2 text-[11px] text-muted-fg">
                      Anchor: <code>{row.anchor_id}</code>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                      <ValueBlock label="Original" value={row.original_value} />
                      <ValueBlock label="Current" value={row.current_value} />
                    </div>
                    <div className="mt-3 flex items-center justify-end">
                      <Button
                        type="button"
                        onClick={() => setOpenAnchor(row.anchor_id)}
                        size="sm"
                      >
                        <History className="mr-1 h-3.5 w-3.5" />
                        View full history
                      </Button>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>

      <AnchorHistoryDrawer
        instanceId={instanceId}
        anchor={openAnchor}
        onClose={() => setOpenAnchor(null)}
      />
    </div>
  );
}
