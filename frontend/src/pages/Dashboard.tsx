import { Link } from "react-router-dom";
import { Play, Plug } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import {
  useBackupNow,
  useBackups,
  useInstances,
  useSchedules,
  useTestConnection,
} from "@/api/queries";
import type { Instance, ScheduleRow } from "@/api/types";

export function Dashboard() {
  const instances = useInstances();
  const schedules = useSchedules();
  const backups = useBackups();

  const backupNow = useBackupNow();
  const test = useTestConnection();

  if (instances.isPending) return <div className="text-sm text-muted-fg">Loading…</div>;
  if (instances.error) return <div className="text-sm text-danger">Failed to load instances.</div>;

  const byId = new Map(schedules.data?.map((s) => [s.instance_id, s]) ?? []);

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <Link to="/instances" className="text-sm text-accent hover:underline">
          Manage instances →
        </Link>
      </div>

      {instances.data!.length === 0 && (
        <div className="mt-8 rounded-lg border border-border bg-muted/30 p-8 text-center">
          <p className="text-sm text-muted-fg">
            No pfSense instances configured yet. Add one from the Instances page.
          </p>
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {instances.data!.map((inst) => (
          <Tile
            key={inst.id}
            instance={inst}
            schedule={byId.get(inst.id)}
            lastBackup={backups.data?.find((b) => b.instance_id === inst.id)}
            onBackupNow={() => backupNow.mutate(inst.id)}
            onTest={() => test.mutate(inst.id)}
            busy={backupNow.isPending || test.isPending}
          />
        ))}
      </div>
    </div>
  );
}

function Tile({
  instance,
  schedule,
  lastBackup,
  onBackupNow,
  onTest,
  busy,
}: {
  instance: Instance;
  schedule?: ScheduleRow;
  lastBackup?: { started_at: string; size_bytes: number; success: boolean };
  onBackupNow: () => void;
  onTest: () => void;
  busy: boolean;
}) {
  return (
    <div className="rounded-lg border border-border bg-muted/30 p-5">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-base font-semibold">{instance.name}</div>
          <div className="mt-0.5 truncate text-xs text-muted-fg">{instance.url}</div>
        </div>
        {instance.enabled ? (
          <Badge tone="success">enabled</Badge>
        ) : (
          <Badge tone="muted">disabled</Badge>
        )}
      </div>

      <dl className="mt-4 space-y-2 text-sm">
        <Row label="Last backup">
          {lastBackup ? (
            <span className={lastBackup.success ? "text-ok" : "text-danger"}>
              {new Date(lastBackup.started_at).toLocaleString()} ·{" "}
              {Math.round(lastBackup.size_bytes / 1024)} KB
            </span>
          ) : (
            <span className="text-muted-fg">never</span>
          )}
        </Row>
        <Row label="Schedule">
          {schedule?.cron_expression ? (
            <span title={schedule.description}>
              {schedule.cron_expression} ({schedule.cron_timezone})
            </span>
          ) : (
            <span className="text-muted-fg">none</span>
          )}
        </Row>
        <Row label="Next run">
          {schedule?.next_runs?.[0] ? (
            new Date(schedule.next_runs[0]).toLocaleString()
          ) : (
            <span className="text-muted-fg">—</span>
          )}
        </Row>
      </dl>

      <div className="mt-4 flex gap-2">
        <Button size="sm" onClick={onBackupNow} disabled={busy}>
          <Play className="h-3.5 w-3.5" />
          Backup Now
        </Button>
        <Button variant="secondary" size="sm" onClick={onTest} disabled={busy}>
          <Plug className="h-3.5 w-3.5" />
          Test
        </Button>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-xs text-muted-fg">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}
