import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Eye, Play, Plug, Split } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { QueryError } from "@/components/ui/QueryError";
import { SplitButton } from "@/components/ui/SplitButton";
import { BackupOverridesDialog } from "@/components/BackupOverridesDialog";
import {
  useBackupNow,
  useBackups,
  useInstance,
  useInstances,
  useJobs,
  useSchedules,
  useTestConnection,
} from "@/api/queries";
import { formatLocal } from "@/lib/datetime";

const STATUS_TONE: Record<string, string> = {
  success: "text-ok",
  running: "text-info",
  queued: "text-muted-fg",
  failure: "text-danger",
  cancelled: "text-muted-fg",
};

export function InstanceDetailPage() {
  const { id: idParam } = useParams();
  const id = Number(idParam);
  const nav = useNavigate();

  const instance = useInstance(Number.isFinite(id) ? id : null);
  const instances = useInstances();
  const schedules = useSchedules();
  const backups = useBackups({ instanceId: id, sort: "started_at", order: "desc" });
  const jobs = useJobs(id);
  const backupNow = useBackupNow();
  const test = useTestConnection();
  const [overridesOpen, setOverridesOpen] = useState(false);

  const schedule = schedules.data?.find((s) => s.instance_id === id);
  const nameOf = useMemo(() => {
    const byId = new Map(instances.data?.map((i) => [i.id, i.name]) ?? []);
    return (nid: number | null | undefined) =>
      nid == null ? "" : byId.get(nid) ?? `id=${nid}`;
  }, [instances.data]);

  const inst = instance.data;

  // Stats derived from the backups list (most recent 100 by default — plenty
  // for a drilldown; older history would need a dedicated aggregate endpoint).
  const stats = useMemo(() => {
    const rows = backups.data ?? [];
    if (rows.length === 0) {
      return {
        count: 0,
        successCount: 0,
        failureCount: 0,
        totalBytes: 0,
        lastSuccess: null as string | null,
      };
    }
    let successCount = 0;
    let failureCount = 0;
    let totalBytes = 0;
    let lastSuccess: string | null = null;
    for (const r of rows) {
      if (r.success) {
        successCount++;
        if (!lastSuccess || r.started_at > lastSuccess) lastSuccess = r.started_at;
      } else {
        failureCount++;
      }
      totalBytes += r.size_bytes;
    }
    return { count: rows.length, successCount, failureCount, totalBytes, lastSuccess };
  }, [backups.data]);

  // Sparkline: last 30 successful backups, size_bytes over time.
  const sparklinePoints = useMemo(() => {
    const rows = (backups.data ?? [])
      .filter((b) => b.success)
      .slice(0, 30)
      .reverse(); // chronological L→R
    if (rows.length < 2) return "";
    const W = 260;
    const H = 48;
    const xs = rows.map((_, i) => (i / (rows.length - 1)) * W);
    const sizes = rows.map((r) => r.size_bytes);
    const min = Math.min(...sizes);
    const max = Math.max(...sizes);
    const range = max - min || 1;
    const ys = sizes.map((s) => H - 4 - ((s - min) / range) * (H - 8));
    return xs.map((x, i) => `${x.toFixed(1)},${ys[i].toFixed(1)}`).join(" ");
  }, [backups.data]);

  if (!Number.isFinite(id)) {
    return <div className="p-6 text-sm text-danger">Invalid instance id.</div>;
  }
  if (instance.isPending) {
    return <div className="p-6 text-sm text-muted-fg">Loading…</div>;
  }
  if (!inst) {
    return <div className="p-6 text-sm text-danger">Instance not found.</div>;
  }

  const busy =
    (backupNow.isPending && backupNow.variables?.id === id) ||
    (test.isPending && test.variables === id);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start justify-between gap-4 border-b border-border pb-3">
        <div className="min-w-0">
          <Link
            to="/instances"
            className="inline-flex items-center gap-1 text-sm text-muted-fg hover:text-accent"
          >
            <ArrowLeft className="h-4 w-4" /> back to instances
          </Link>
          <h1 className="mt-1 text-xl font-semibold">
            {inst.name}{" "}
            {inst.enabled ? (
              <Badge tone="success">enabled</Badge>
            ) : (
              <Badge tone="muted">disabled</Badge>
            )}
          </h1>
          <div className="mt-1 truncate font-mono text-xs text-muted-fg">{inst.url}</div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <SplitButton
            primaryLabel="Backup now"
            primaryIcon={<Play className="h-4 w-4" />}
            onPrimary={() => backupNow.mutate({ id })}
            disabled={busy}
            size="sm"
            menu={[
              {
                label: "Backup now with options…",
                onSelect: () => setOverridesOpen(true),
              },
            ]}
          />
          <Button variant="secondary" size="sm" onClick={() => test.mutate(id)} disabled={busy}>
            <Plug className="h-4 w-4" /> Test
          </Button>
        </div>
      </div>

      {overridesOpen && (
        <BackupOverridesDialog
          title={`Backup ${inst.name} with options`}
          mode="single"
          onClose={() => setOverridesOpen(false)}
          onRun={async (overrides) => {
            await backupNow.mutateAsync({ id, overrides });
          }}
        />
      )}

      {/* Stats grid */}
      <div className="mt-5 grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Backups" value={stats.count.toLocaleString()} />
        <Stat
          label="Success rate"
          value={
            stats.count === 0
              ? "—"
              : `${((stats.successCount / stats.count) * 100).toFixed(0)}%`
          }
          tone={stats.failureCount > 0 ? "warn" : "ok"}
        />
        <Stat
          label="Total size"
          value={
            stats.totalBytes === 0
              ? "—"
              : `${(stats.totalBytes / 1024 / 1024).toFixed(1)} MB`
          }
        />
        <Stat
          label="Last success"
          value={
            stats.lastSuccess ? formatLocal(stats.lastSuccess) : "never"
          }
        />
      </div>

      {/* Schedule + sparkline side by side */}
      <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-border bg-muted/20 p-4">
          <div className="text-xs uppercase tracking-wider text-muted-fg">Schedule</div>
          <div className="mt-2 font-mono text-sm">
            {inst.cron_expression ?? <span className="text-muted-fg">none</span>}
            {inst.cron_expression && schedule?.effective_timezone && (
              <span className="ml-2 text-xs text-muted-fg">
                ({schedule.effective_timezone}
                {inst.cron_timezone === null && " · global"})
              </span>
            )}
          </div>
          {schedule?.description && (
            <div className="mt-1 text-xs text-muted-fg">{schedule.description}</div>
          )}
          {schedule?.next_runs?.[0] && (
            <div className="mt-2 text-xs">
              <span className="text-muted-fg">Next: </span>
              {new Date(schedule.next_runs[0]).toLocaleString()}
            </div>
          )}
        </div>
        <div className="rounded-lg border border-border bg-muted/20 p-4">
          <div className="text-xs uppercase tracking-wider text-muted-fg">
            Size trend (last {Math.min(30, backups.data?.filter((b) => b.success).length ?? 0)})
          </div>
          {sparklinePoints ? (
            <svg width="100%" viewBox="0 0 260 48" className="mt-2 w-full">
              <polyline
                points={sparklinePoints}
                fill="none"
                stroke="hsl(var(--accent))"
                strokeWidth="1.5"
              />
            </svg>
          ) : (
            <div className="mt-2 text-sm text-muted-fg">
              Not enough successful backups to chart yet.
            </div>
          )}
        </div>
      </div>

      {/* Recent backups */}
      <h2 className="mt-6 text-sm font-semibold uppercase tracking-wider text-muted-fg">
        Recent backups
      </h2>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs uppercase text-muted-fg">
            <tr>
              <th className="text-left font-normal">Started</th>
              <th className="text-left font-normal">File</th>
              <th className="text-left font-normal">Contents</th>
              <th className="text-left font-normal">Size</th>
              <th className="text-left font-normal">Duration</th>
              <th className="text-left font-normal">Tag</th>
              <th className="text-left font-normal">Status</th>
              <th className="w-10"></th>
            </tr>
          </thead>
          <tbody>
            {(backups.data ?? []).slice(0, 15).map((b) => (
              <tr key={b.id} className="border-t border-border">
                <td className="py-2 text-xs">{formatLocal(b.started_at)}</td>
                <td className="py-2 font-mono text-xs">{b.filename}</td>
                <td className="py-2">
                  <span className="inline-flex flex-wrap items-center gap-1">
                    {b.area && <Badge tone="muted" title={`Area: ${b.area}`}>{b.area}</Badge>}
                    {b.included_rrd && <Badge tone="success" title="Includes RRD">RRD</Badge>}
                    {b.included_packages && <Badge tone="success" title="Includes packages">pkgs</Badge>}
                    {b.included_ssh && <Badge tone="success" title="Includes SSH keys">ssh</Badge>}
                    {b.encrypted && <Badge tone="warn" title="Encrypted at rest">encrypted</Badge>}
                  </span>
                </td>
                <td className="py-2">{Math.round(b.size_bytes / 1024)} KB</td>
                <td className="py-2 text-xs">{b.duration_seconds.toFixed(1)}s</td>
                <td className="py-2">
                  {b.tag ? (
                    <span className="rounded-full border border-accent/50 bg-accent/10 px-2 py-0.5 text-xs text-accent">
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
                <td className="py-2 text-right">
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
                </td>
              </tr>
            ))}
            {backups.isError && (
              <tr>
                <td colSpan={8} className="py-4">
                  <QueryError title="Could not load backups" error={backups.error} />
                </td>
              </tr>
            )}
            {!backups.isError && (backups.data ?? []).length === 0 && (
              <tr>
                <td colSpan={8} className="py-8 text-center text-sm text-muted-fg">
                  No backups yet for {inst.name}.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-4 text-xs">
        {(backups.data ?? []).length > 0 && (
          <Link
            to={`/instances/${id}/history`}
            className="inline-flex items-center gap-1 text-muted-fg hover:text-accent"
          >
            scrub through history →
          </Link>
        )}
        {(backups.data ?? []).length > 15 && (
          <Link
            to={`/backups?instance=${id}`}
            className="inline-flex items-center gap-1 text-muted-fg hover:text-accent"
          >
            <Split className="h-3 w-3" /> view all backups for this instance
          </Link>
        )}
      </div>

      {/* Recent jobs */}
      <h2 className="mt-6 text-sm font-semibold uppercase tracking-wider text-muted-fg">
        Recent jobs
      </h2>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs uppercase text-muted-fg">
            <tr>
              <th className="text-left font-normal">Requested</th>
              <th className="text-left font-normal">Kind</th>
              <th className="text-left font-normal">By</th>
              <th className="text-left font-normal">Status</th>
              <th className="text-left font-normal">Message</th>
            </tr>
          </thead>
          <tbody>
            {(jobs.data ?? []).slice(0, 10).map((j) => (
              <tr key={j.id} className="border-t border-border">
                <td className="py-2 text-xs">{formatLocal(j.requested_at)}</td>
                <td className="py-2 text-xs">{j.kind}</td>
                <td className="py-2 text-xs text-muted-fg">{j.requested_by ?? "—"}</td>
                <td className={`py-2 text-xs font-medium ${STATUS_TONE[j.status] ?? ""}`}>
                  {j.status}
                </td>
                <td className="py-2 text-xs text-muted-fg">{j.message ?? ""}</td>
              </tr>
            ))}
            {jobs.isError && (
              <tr>
                <td colSpan={5} className="py-4">
                  <QueryError title="Could not load jobs" error={jobs.error} />
                </td>
              </tr>
            )}
            {!jobs.isError && (jobs.data ?? []).length === 0 && (
              <tr>
                <td colSpan={5} className="py-8 text-center text-sm text-muted-fg">
                  No jobs recorded for {inst.name} yet. (Background reference: {nameOf(id)})
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "ok" | "warn" | "danger";
}) {
  const toneClass =
    tone === "ok" ? "text-ok" : tone === "warn" ? "text-warn" : tone === "danger" ? "text-danger" : "";
  return (
    <div className="rounded-lg border border-border bg-muted/20 p-4">
      <div className="text-xs uppercase tracking-wider text-muted-fg">{label}</div>
      <div className={`mt-1 text-xl font-semibold ${toneClass}`}>{value}</div>
    </div>
  );
}
