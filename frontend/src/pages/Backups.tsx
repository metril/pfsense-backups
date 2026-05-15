import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Controller, useForm, useWatch } from "react-hook-form";
import {
  Archive,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Download,
  Eye,
  KeyRound,
  Lock,
  Split,
  Tag as TagIcon,
  Trash2,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { Label } from "@/components/ui/Label";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { FormCheckbox, FormInput } from "@/components/ui/form";
import { useDebouncedValue } from "@/lib/useDebouncedValue";
import {
  useBackups,
  useDeleteBackup,
  useInstances,
  useReencryptAll,
  type BackupFilter,
  type BackupOrder,
  type BackupSort,
} from "@/api/queries";
import { api, triggerDownload } from "@/api/client";
import type { BackupListItem } from "@/api/types";
import { cn } from "@/lib/cn";
import { formatLocal } from "@/lib/datetime";

// Convert a <input type="date"> value (YYYY-MM-DD, local) into an ISO-8601
// boundary suitable for the started_from / started_to query params. "from"
// pins to 00:00 local, "to" pins to 23:59:59.999 local so the end-date is
// inclusive the way a user expects.
function boundary(d: string, end: boolean): string | undefined {
  if (!d) return undefined;
  const [y, m, dd] = d.split("-").map(Number);
  if (!y || !m || !dd) return undefined;
  const date = new Date(y, m - 1, dd, end ? 23 : 0, end ? 59 : 0, end ? 59 : 0, end ? 999 : 0);
  return date.toISOString();
}

type BackupsFilterForm = {
  instanceId: string;
  fromDate: string;
  toDate: string;
};

export function BackupsPage() {
  const { control, setValue } = useForm<BackupsFilterForm>({
    defaultValues: { instanceId: "", fromDate: "", toDate: "" },
  });
  // Per-field subscriptions: BackupsPage only re-renders when an
  // individual filter value actually changes (not on every keystroke
  // into an unrelated field).
  const instanceIdStr = useWatch({ control, name: "instanceId" });
  const fromDate = useWatch({ control, name: "fromDate" });
  const toDate = useWatch({ control, name: "toDate" });
  const [sort, setSort] = useState<BackupSort>("started_at");
  const [order, setOrder] = useState<BackupOrder>("desc");

  // Debounce the date inputs so each keystroke doesn't fire an API call.
  const debouncedFromDate = useDebouncedValue(fromDate, 300);
  const debouncedToDate = useDebouncedValue(toDate, 300);

  const instanceId =
    instanceIdStr === "" ? undefined : Number(instanceIdStr);
  const filter: BackupFilter = {
    instanceId,
    startedFrom: boundary(debouncedFromDate, false),
    startedTo: boundary(debouncedToDate, true),
    sort,
    order,
  };
  const backups = useBackups(filter);
  const instances = useInstances();
  const del = useDeleteBackup();
  const reencryptAll = useReencryptAll();
  const confirm = useConfirm();
  const toast = useToast();
  const nav = useNavigate();
  const [reencryptOpen, setReencryptOpen] = useState(false);

  // M9: preserve selection ORDER — the first-selected row is "A" in the diff
  // and the second-selected is "B", rather than silently sorting by id.
  const [selectedList, setSelectedList] = useState<number[]>([]);
  const selected = useMemo(() => new Set(selectedList), [selectedList]);
  const rows = backups.data ?? [];
  const canDiff = selectedList.length === 2;
  const hasDateFilter = Boolean(fromDate || toDate);

  function toggle(id: number) {
    setSelectedList((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  async function downloadSelected() {
    if (selectedList.length === 0) return;
    if (selectedList.length === 1) {
      const [id] = selectedList;
      const row = rows.find((r) => r.id === id)!;
      const blob = await api.downloadBlob(`/api/backups/${id}/download`);
      triggerDownload(blob, row.filename);
    } else {
      // H2: use the unified helper so CSRF + 401 handling stay in one place.
      const blob = await api.postForBlob("/api/backups/download-zip", {
        ids: selectedList,
      });
      triggerDownload(blob, "pfsense-backups.zip");
    }
  }

  function diffSelected() {
    if (!canDiff) return;
    const [a, b] = selectedList;
    nav(`/backups/diff/${a}/${b}`);
  }

  function clickSort(col: BackupSort) {
    if (col === sort) {
      setOrder(order === "asc" ? "desc" : "asc");
    } else {
      setSort(col);
      // Size / duration tend to be read desc (largest first); dates default
      // desc; filename is alphabetical so asc is more intuitive.
      setOrder(col === "filename" ? "asc" : "desc");
    }
  }

  function sortIcon(col: BackupSort) {
    if (col !== sort) return <ArrowUpDown className="h-3 w-3 opacity-40" />;
    return order === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />;
  }

  async function deleteBackup(id: number, filename: string) {
    const ok = await confirm({
      title: `Delete ${filename}?`,
      description:
        "The DB row AND the XML file on disk will be removed. " +
        "This cannot be undone by the app — restore would require manually " +
        "placing the file back.",
      confirmLabel: "Delete",
      tone: "danger",
    });
    if (!ok) return;
    setSelectedList((prev) => prev.filter((x) => x !== id));
    del.mutate(id);
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Backups</h1>
        <div className="flex flex-wrap gap-2">
          <Controller
            control={control}
            name="instanceId"
            render={({ field }) => (
              <select
                value={field.value}
                onChange={field.onChange}
                className="h-9 rounded-md border border-border bg-bg px-2 text-sm"
                aria-label="Instance filter"
              >
                <option value="">All instances</option>
                {instances.data?.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.name}
                  </option>
                ))}
              </select>
            )}
          />
          <div className="flex items-center gap-1 rounded-md border border-border bg-bg px-2 text-sm">
            <span className="text-muted-fg">from</span>
            <Controller
              control={control}
              name="fromDate"
              render={({ field }) => (
                <input
                  type="date"
                  value={field.value}
                  onChange={field.onChange}
                  className="h-9 bg-transparent text-sm outline-none"
                  aria-label="Started from"
                />
              )}
            />
            <span className="text-muted-fg">to</span>
            <Controller
              control={control}
              name="toDate"
              render={({ field }) => (
                <input
                  type="date"
                  value={field.value}
                  onChange={field.onChange}
                  className="h-9 bg-transparent text-sm outline-none"
                  aria-label="Started to"
                />
              )}
            />
            {hasDateFilter && (
              <button
                type="button"
                onClick={() => {
                  setValue("fromDate", "");
                  setValue("toDate", "");
                }}
                className="rounded p-1 text-muted-fg hover:text-fg"
                aria-label="Clear date filter"
                title="Clear date filter"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={downloadSelected}
            disabled={selectedList.length === 0}
          >
            {selectedList.length > 1 ? (
              <Archive className="h-4 w-4" />
            ) : (
              <Download className="h-4 w-4" />
            )}
            Download ({selectedList.length})
          </Button>
          <Button size="sm" onClick={diffSelected} disabled={!canDiff}>
            <Split className="h-4 w-4" />
            Diff selected
          </Button>
          {/* Danger tone at the trigger so an operator scanning the
              toolbar sees the destructive affordance before clicking —
              tooltip text alone is invisible on touch devices. The
              ``ConfirmDialog`` still gates the actual submission, but
              a missed click shouldn't look innocuous. */}
          <Button
            variant="danger"
            size="sm"
            onClick={() => setReencryptOpen(true)}
            title="Re-encrypt every encrypted backup with a new password"
          >
            <KeyRound className="h-4 w-4" />
            Re-encrypt all…
          </Button>
        </div>
      </div>

      {/* v0.45.0: the API no longer caps at 100 — long-history
          deployments may render a 1000+ row table. Surface the count
          + a nudge toward the filters when that gets heavy. */}
      {rows.length > 200 && (
        <div className="mt-3 text-xs text-muted-fg">
          Showing {rows.length.toLocaleString()} backups — narrow with the
          instance filter or date range above to scroll less.
        </div>
      )}

      <table className="mt-6 w-full text-sm">
        <thead className="text-xs uppercase text-muted-fg">
          <tr>
            <th className="w-6 px-3"></th>
            <th className="px-3 text-left font-normal">Instance</th>
            <SortHeader label="Started" col="started_at" current={sort} order={order} onClick={clickSort} icon={sortIcon} className="px-3" />
            <SortHeader label="Duration" col="duration_seconds" current={sort} order={order} onClick={clickSort} icon={sortIcon} className="px-3" />
            <SortHeader label="File" col="filename" current={sort} order={order} onClick={clickSort} icon={sortIcon} className="px-3" />
            <th className="px-3 text-left font-normal">Contents</th>
            <SortHeader label="Size" col="size_bytes" current={sort} order={order} onClick={clickSort} icon={sortIcon} className="px-3" />
            <th className="px-3 text-left font-normal">Tag</th>
            <th className="px-3 text-left font-normal">Status</th>
            <th className="w-20 px-3"></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((b) => (
            <tr key={b.id} className="border-t border-border align-middle">
              <td className="px-3">
                <input
                  type="checkbox"
                  // M11: ensure visible contrast on the dark theme. Default
                  // browser styling nearly disappears on bg-bg.
                  className="h-4 w-4 cursor-pointer accent-accent"
                  checked={selected.has(b.id)}
                  onChange={() => toggle(b.id)}
                  disabled={!b.success}
                  aria-label={`Select backup ${b.filename}`}
                />
              </td>
              <td className="px-3 py-2">
                <Link to="/instances" className="hover:text-accent">
                  {b.instance_name}
                </Link>
              </td>
              <td className="px-3 py-2 text-xs whitespace-nowrap">
                {formatLocal(b.started_at)}
              </td>
              <td className="px-3 py-2 text-xs tabular-nums whitespace-nowrap">
                {b.duration_seconds.toFixed(1)}s
              </td>
              <td className="px-3 py-2 font-mono text-xs">
                {b.success ? (
                  <Link to={`/backups/${b.id}/view`} className="hover:text-accent">
                    {b.filename}
                  </Link>
                ) : (
                  b.filename
                )}
              </td>
              <td className="px-3 py-2">
                <ContentsBadges b={b} />
              </td>
              <td className="px-3 py-2 tabular-nums whitespace-nowrap">
                {Math.round(b.size_bytes / 1024)} KB
              </td>
              <td className="px-3 py-2">
                {b.tag ? (
                  <span className="inline-flex items-center gap-1 rounded-full border border-accent/50 bg-accent/10 px-2 py-0.5 text-xs text-accent">
                    <TagIcon className="h-3 w-3" />
                    {b.tag}
                  </span>
                ) : (
                  <span className="text-muted-fg">—</span>
                )}
              </td>
              <td className="px-3 py-2">
                {b.success ? (
                  <Badge tone="success">ok</Badge>
                ) : (
                  <Badge tone="danger">fail</Badge>
                )}
              </td>
              <td className="px-3 py-2">
                <div className="flex justify-end gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => nav(`/backups/${b.id}/view`)}
                    disabled={!b.success}
                    aria-label={`View ${b.filename}`}
                    title="View XML"
                  >
                    <Eye className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => deleteBackup(b.id, b.filename)}
                    aria-label={`Delete ${b.filename}`}
                    title="Delete"
                  >
                    <Trash2 className="h-4 w-4 text-danger" />
                  </Button>
                </div>
              </td>
            </tr>
          ))}
          {backups.isPending &&
            Array.from({ length: 5 }).map((_, i) => (
              <tr key={`sk-${i}`} className="border-t border-border">
                <td colSpan={10} className="py-2">
                  <Skeleton className="h-6 w-full" />
                </td>
              </tr>
            ))}
        </tbody>
      </table>
      {!backups.isPending && rows.length === 0 && (
        <div className="mt-8">
          <EmptyState
            icon={<Archive className="h-8 w-8" />}
            headline={hasDateFilter ? "No backups in that date range" : "No backups yet"}
            body={
              hasDateFilter
                ? "Widen the date filter or clear it to see more."
                : "Once an instance runs its first backup (manually or on its schedule), it will show up here."
            }
            cta={
              hasDateFilter ? (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    setValue("fromDate", "");
                    setValue("toDate", "");
                  }}
                >
                  Clear date filter
                </Button>
              ) : undefined
            }
          />
        </div>
      )}

      {reencryptOpen && (
        <ReencryptAllDialog
          encryptedCount={rows.filter((r) => r.encrypted).length}
          instanceCount={
            new Set(rows.filter((r) => r.encrypted).map((r) => r.instance_id)).size
          }
          onClose={() => setReencryptOpen(false)}
          onConfirm={async (payload) => {
            const r = await reencryptAll.mutateAsync(payload);
            toast.info(
              `Job #${r.job_id} is re-encrypting all encrypted backups. Watch progress in the Jobs page.`,
              "Re-encryption started",
            );
            setReencryptOpen(false);
          }}
        />
      )}
    </div>
  );
}

function ContentsBadges({ b }: { b: BackupListItem }) {
  // v0.41.3: each flag-badge is ALWAYS rendered in DOM but the
  // absent ones carry the ``invisible`` class (``visibility:
  // hidden`` — preserves layout width). That keeps each badge
  // TYPE in a fixed column position across rows — ``pkgs`` is
  // always at slot A, ``ssh`` at slot B, etc.
  //
  // v0.41.4: slot ordering matters. The ``CONTENTS`` header is
  // left-aligned at column-x=0, so the leftmost slot needs to
  // match the badge operators typically see at the left of the
  // cluster. Order is now: pkgs, ssh, encrypted (the common
  // toggleable trio), then gz, RRD (rare). ``area`` is variable-
  // width (string label, not a boolean flag) so it stays
  // conditionally rendered, moved to the TRAILING position so it
  // doesn't push the fixed slots right.
  // v0.41.9: ``visibility: hidden`` (from the ``invisible`` class)
  // preserves layout but does NOT remove the element from the
  // accessibility tree. Without ``aria-hidden``, screen readers
  // would still announce every placeholder's ``title`` text (e.g.
  // "Includes SSH host keys") on rows that DON'T include SSH keys
  // — exactly the opposite of what the layout claims. ``ariaHidden``
  // on the placeholders also suppresses the native browser title
  // tooltip, so a sighted mouse user can't accidentally hover up an
  // incorrect hint on a hidden chip.
  const hidden = (present: boolean) => (present ? "" : "invisible");
  return (
    <span className="inline-flex items-center gap-1 align-middle whitespace-nowrap">
      <Badge
        tone="muted"
        className={hidden(b.included_packages)}
        title="Includes package information"
        ariaHidden={!b.included_packages}
      >
        pkgs
      </Badge>
      <Badge
        tone="muted"
        className={hidden(b.included_ssh)}
        title="Includes SSH host keys"
        ariaHidden={!b.included_ssh}
      >
        ssh
      </Badge>
      <Badge
        tone="warn"
        className={hidden(b.encrypted)}
        title="Encrypted at rest — view decrypts in memory"
        ariaHidden={!b.encrypted}
      >
        <span className="inline-flex items-center gap-1">
          <Lock className="h-3 w-3" />
          encrypted
        </span>
      </Badge>
      <Badge
        tone="muted"
        className={hidden(b.compressed)}
        title="gzip-compressed at rest"
        ariaHidden={!b.compressed}
      >
        gz
      </Badge>
      <Badge
        tone="muted"
        className={hidden(b.included_rrd)}
        title="Includes RRD graph data"
        ariaHidden={!b.included_rrd}
      >
        RRD
      </Badge>
      {b.area && (
        <Badge tone="muted" title={`pfSense backup area: ${b.area}`}>
          {b.area}
        </Badge>
      )}
    </span>
  );
}

type ReencryptForm = {
  pw: string;
  confirmPw: string;
  alsoUpdate: boolean;
};

function ReencryptAllDialog({
  encryptedCount,
  instanceCount,
  onClose,
  onConfirm,
}: {
  encryptedCount: number;
  instanceCount: number;
  onClose: () => void;
  onConfirm: (p: {
    new_password: string;
    confirm_password: string;
    also_update_instance_passwords: boolean;
  }) => Promise<void>;
}) {
  const { control, handleSubmit, watch } = useForm<ReencryptForm>({
    defaultValues: { pw: "", confirmPw: "", alsoUpdate: true },
  });
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const pw = watch("pw");
  const confirmPw = watch("confirmPw");
  const mismatch = pw !== confirmPw && confirmPw.length > 0;
  const canSubmit =
    pw.length > 0 && !mismatch && pw === confirmPw && !submitting;

  const onSubmit = handleSubmit(async (data) => {
    if (!canSubmit) return;
    setErr(null);
    setSubmitting(true);
    try {
      await onConfirm({
        new_password: data.pw,
        confirm_password: data.confirmPw,
        also_update_instance_passwords: data.alsoUpdate,
      });
    } catch (e) {
      setErr(String(e));
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title="Re-encrypt all backups"
      tone="warn"
    >
      <form onSubmit={onSubmit} noValidate>
        <div className="space-y-3">
          <p className="text-sm text-muted-fg">
            {encryptedCount === 0
              ? "No encrypted backups are visible in the current filter, but the worker re-encrypts every encrypted row it finds across the entire fleet."
              : `${encryptedCount} visible encrypted backup(s) across ${instanceCount} instance(s) will be re-encrypted with the new password.`}
            {" "}
            The old password will no longer decrypt those files. This cannot be undone by the app.
          </p>
          <div>
            <Label>New encryption password</Label>
            <FormInput control={control} name="pw" type="password" />
          </div>
          <div>
            <Label>Confirm password</Label>
            <FormInput control={control} name="confirmPw" type="password" />
            {mismatch && (
              <p className="mt-1 text-xs text-danger">Passwords don't match.</p>
            )}
          </div>
          <FormCheckbox
            control={control}
            name="alsoUpdate"
            label="Also update every instance's stored password to this one."
            className="items-start"
          />
          {err && (
            <p className="text-xs text-danger">{err}</p>
          )}
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={!canSubmit}>
            {submitting ? "Starting…" : "Re-encrypt all"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function SortHeader({
  label,
  col,
  current,
  order,
  onClick,
  icon,
  className,
}: {
  label: string;
  col: BackupSort;
  current: BackupSort;
  order: BackupOrder;
  onClick: (c: BackupSort) => void;
  icon: (c: BackupSort) => React.ReactNode;
  /** v0.41.3: horizontal padding / extra classes passed through to
   *  the ``<th>``. Used to keep sortable headers in lockstep with
   *  the non-sortable ones that get ``px-3`` for column breathing
   *  room. */
  className?: string;
}) {
  // aria-sort belongs on the <th>, not the <button>. Correctly reflect
  // the *actual* direction (order) when this column is active; "none"
  // otherwise — WAI-ARIA sortable column semantics.
  const ariaSort =
    col !== current ? "none" : order === "asc" ? "ascending" : "descending";
  // v0.41.4: every header is uniformly ``text-left``. Previously
  // Duration and Size were ``text-right`` — that pushed their
  // short values (``1.6s``, ``272 KB``) to the column's right
  // edge, leaving a large visual gap between the date in STARTED
  // and the value in DURATION, and making SIZE / TAG labels
  // converge in the middle of their gap. Left-align everywhere
  // keeps headers over their own column's content.
  return (
    <th className={cn("text-left font-normal", className)} aria-sort={ariaSort}>
      <button
        type="button"
        onClick={() => onClick(col)}
        className={cn(
          "inline-flex items-center gap-1 uppercase tracking-wider hover:text-fg",
          col === current && "text-fg",
        )}
      >
        {label}
        {icon(col)}
      </button>
    </th>
  );
}
