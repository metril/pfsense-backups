import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Archive, Download, Split } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useBackups, useInstances } from "@/api/queries";
import { api, triggerDownload } from "@/api/client";

export function BackupsPage() {
  const [instanceId, setInstanceId] = useState<number | undefined>(undefined);
  const backups = useBackups(instanceId);
  const instances = useInstances();
  const nav = useNavigate();

  const [selected, setSelected] = useState<Set<number>>(new Set());
  const rows = backups.data ?? [];
  const canDiff = selected.size === 2;

  const selectedIds = useMemo(() => [...selected], [selected]);

  function toggle(id: number) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  }

  async function downloadSelected() {
    if (selected.size === 0) return;
    if (selected.size === 1) {
      const [id] = selectedIds;
      const row = rows.find((r) => r.id === id)!;
      const blob = await api.downloadBlob(`/api/backups/${id}/download`);
      triggerDownload(blob, row.filename);
    } else {
      // H2: use the unified helper so CSRF + 401 handling stay in one place.
      const blob = await api.postForBlob("/api/backups/download-zip", {
        ids: selectedIds,
      });
      triggerDownload(blob, "pfsense-backups.zip");
    }
  }

  function diffSelected() {
    if (!canDiff) return;
    const [a, b] = selectedIds.sort((x, y) => x - y);
    nav(`/backups/diff/${a}/${b}`);
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Backups</h1>
        <div className="flex gap-2">
          <select
            value={instanceId ?? ""}
            onChange={(e) => setInstanceId(e.target.value ? Number(e.target.value) : undefined)}
            className="h-9 rounded-md border border-border bg-bg px-2 text-sm"
          >
            <option value="">All instances</option>
            {instances.data?.map((i) => (
              <option key={i.id} value={i.id}>{i.name}</option>
            ))}
          </select>
          <Button variant="secondary" size="sm" onClick={downloadSelected} disabled={selected.size === 0}>
            {selected.size > 1 ? <Archive className="h-4 w-4" /> : <Download className="h-4 w-4" />}
            Download ({selected.size})
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
            <th className="text-left font-normal">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((b) => (
            <tr key={b.id} className="border-t border-border">
              <td>
                <input
                  type="checkbox"
                  checked={selected.has(b.id)}
                  onChange={() => toggle(b.id)}
                  disabled={!b.success}
                />
              </td>
              <td className="py-2">
                <Link to={`/instances`} className="hover:text-accent">{b.instance_name}</Link>
              </td>
              <td className="py-2 text-xs">{new Date(b.started_at).toLocaleString()}</td>
              <td className="py-2 text-xs">{b.duration_seconds.toFixed(1)}s</td>
              <td className="py-2 font-mono text-xs">
                {b.filename} {b.compressed && <Badge tone="muted">gz</Badge>}
              </td>
              <td className="py-2">{Math.round(b.size_bytes / 1024)} KB</td>
              <td className="py-2">
                {b.success ? <Badge tone="success">ok</Badge> : <Badge tone="danger">fail</Badge>}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={7} className="py-8 text-center text-sm text-muted-fg">
                No backups yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
