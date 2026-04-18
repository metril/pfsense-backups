import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Archive, Download, Eye, Split, Tag as TagIcon, Trash2, X } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import {
  useBackups,
  useDeleteBackup,
  useInstances,
  type BackupFilter,
} from "@/api/queries";
import { api, triggerDownload } from "@/api/client";

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

export function BackupsPage() {
  const [instanceId, setInstanceId] = useState<number | undefined>(undefined);
  const [fromDate, setFromDate] = useState<string>("");
  const [toDate, setToDate] = useState<string>("");

  const filter: BackupFilter = {
    instanceId,
    startedFrom: boundary(fromDate, false),
    startedTo: boundary(toDate, true),
  };
  const backups = useBackups(filter);
  const instances = useInstances();
  const del = useDeleteBackup();
  const confirm = useConfirm();
  const nav = useNavigate();

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
          <select
            value={instanceId ?? ""}
            onChange={(e) => setInstanceId(e.target.value ? Number(e.target.value) : undefined)}
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
          <div className="flex items-center gap-1 rounded-md border border-border bg-bg px-2 text-sm">
            <span className="text-muted-fg">from</span>
            <input
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              className="h-9 bg-transparent text-sm outline-none"
              aria-label="Started from"
            />
            <span className="text-muted-fg">to</span>
            <input
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              className="h-9 bg-transparent text-sm outline-none"
              aria-label="Started to"
            />
            {hasDateFilter && (
              <button
                type="button"
                onClick={() => {
                  setFromDate("");
                  setToDate("");
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
        </div>
      </div>

      <table className="mt-6 w-full text-sm">
        <thead className="text-xs uppercase text-muted-fg">
          <tr>
            <th className="w-6"></th>
            <th className="text-left font-normal">Instance</th>
            <th className="text-left font-normal">Started</th>
            <th className="text-left font-normal">Duration</th>
            <th className="text-left font-normal">File</th>
            <th className="text-left font-normal">Size</th>
            <th className="text-left font-normal">Tag</th>
            <th className="text-left font-normal">Status</th>
            <th className="w-20"></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((b) => (
            <tr key={b.id} className="border-t border-border">
              <td>
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
              <td className="py-2">
                <Link to="/instances" className="hover:text-accent">
                  {b.instance_name}
                </Link>
              </td>
              <td className="py-2 text-xs">{new Date(b.started_at).toLocaleString()}</td>
              <td className="py-2 text-xs">{b.duration_seconds.toFixed(1)}s</td>
              <td className="py-2 font-mono text-xs">
                {b.success ? (
                  <Link to={`/backups/${b.id}/view`} className="hover:text-accent">
                    {b.filename}
                  </Link>
                ) : (
                  b.filename
                )}{" "}
                {b.compressed && <Badge tone="muted">gz</Badge>}
              </td>
              <td className="py-2">{Math.round(b.size_bytes / 1024)} KB</td>
              <td className="py-2">
                {b.tag ? (
                  <span className="inline-flex items-center gap-1 rounded-full border border-accent/50 bg-accent/10 px-2 py-0.5 text-xs text-accent">
                    <TagIcon className="h-3 w-3" />
                    {b.tag}
                  </span>
                ) : (
                  <span className="text-muted-fg">—</span>
                )}
              </td>
              <td className="py-2">
                {b.success ? (
                  <Badge tone="success">ok</Badge>
                ) : (
                  <Badge tone="danger">fail</Badge>
                )}
              </td>
              <td className="py-2">
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
          {rows.length === 0 && (
            <tr>
              <td colSpan={9} className="py-8 text-center text-sm text-muted-fg">
                {hasDateFilter
                  ? "No backups in that date range."
                  : "No backups yet."}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
