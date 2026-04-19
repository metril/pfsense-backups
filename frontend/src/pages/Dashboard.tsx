import { useState } from "react";
import { Link } from "react-router-dom";
import { Play, PlayCircle, Plug, Settings2 } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { BackupOverridesDialog } from "@/components/BackupOverridesDialog";
import {
  useBackupAll,
  useBackupNow,
  useBackups,
  useInstances,
  useSchedules,
  useTestConnection,
} from "@/api/queries";
import type { BackupOverridesRequest, Instance, ScheduleRow } from "@/api/types";

export function Dashboard() {
  const instances = useInstances();
  const schedules = useSchedules();
  const backups = useBackups();

  const backupNow = useBackupNow();
  const backupAll = useBackupAll();
  const test = useTestConnection();

  // Which dialog is open: "all" (top-bar), a number = instance id, or null.
  const [overridesOpen, setOverridesOpen] = useState<"all" | number | null>(null);

  if (instances.isPending) return <div className="text-sm text-muted-fg">Loading…</div>;
  if (instances.error) return <div className="text-sm text-danger">Failed to load instances.</div>;

  const byId = new Map(schedules.data?.map((s) => [s.instance_id, s]) ?? []);

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1">
            <Button
              size="sm"
              onClick={() => backupAll.mutate(undefined)}
              disabled={backupAll.isPending || (instances.data?.length ?? 0) === 0}
              title="Back up every enabled instance in parallel"
            >
              <PlayCircle className="h-4 w-4" />
              {backupAll.isPending ? "Starting…" : "Backup all"}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setOverridesOpen("all")}
              disabled={backupAll.isPending || (instances.data?.length ?? 0) === 0}
              aria-label="Backup all with options"
              title="Backup all with options…"
            >
              <Settings2 className="h-4 w-4" />
            </Button>
          </div>
          <Link to="/instances" className="text-sm text-accent hover:underline">
            Manage instances →
          </Link>
        </div>
      </div>

      {instances.data!.length === 0 && (
        <div className="mt-8 rounded-lg border border-border bg-muted/30 p-8 text-center">
          <p className="text-sm text-muted-fg">
            No pfSense instances configured yet. Add one from the Instances page.
          </p>
        </div>
      )}

      {overridesOpen !== null && (
        <BackupOverridesDialog
          key={String(overridesOpen)}
          title={
            overridesOpen === "all"
              ? "Backup all with options"
              : `Backup ${instances.data!.find((i) => i.id === overridesOpen)?.name ?? ""} with options`
          }
          mode={overridesOpen === "all" ? "all" : "single"}
          onClose={() => setOverridesOpen(null)}
          onRun={async (overrides: BackupOverridesRequest | undefined) => {
            if (overridesOpen === "all") {
              await backupAll.mutateAsync(overrides);
            } else {
              await backupNow.mutateAsync({ id: overridesOpen, overrides });
            }
          }}
        />
      )}

      <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {instances.data!.map((inst) => (
          <Tile
            key={inst.id}
            instance={inst}
            schedule={byId.get(inst.id)}
            lastBackup={backups.data?.find((b) => b.instance_id === inst.id)}
            onBackupNow={() => backupNow.mutate({ id: inst.id })}
            onBackupNowWithOptions={() => setOverridesOpen(inst.id)}
            onTest={() => test.mutate(inst.id)}
            // H3: per-instance busy flag. TanStack Query exposes the last
            // mutation's `variables`; compare to this tile's id so clicking
            // one tile doesn't freeze every tile's buttons.
            busy={
              (backupNow.isPending && backupNow.variables?.id === inst.id) ||
              (test.isPending && test.variables === inst.id)
            }
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
  onBackupNowWithOptions,
  onTest,
  busy,
}: {
  instance: Instance;
  schedule?: ScheduleRow;
  lastBackup?: { started_at: string; size_bytes: number; success: boolean };
  onBackupNow: () => void;
  onBackupNowWithOptions: () => void;
  onTest: () => void;
  busy: boolean;
}) {
  return (
    <div className="rounded-lg border border-border bg-muted/30 p-5">
      <div className="flex items-start justify-between gap-2">
        <div>
          <Link
            to={`/instances/${instance.id}`}
            className="text-base font-semibold hover:text-accent"
          >
            {instance.name}
          </Link>
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
              {schedule.cron_expression} ({schedule.effective_timezone})
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
        <Button
          variant="ghost"
          size="icon"
          onClick={onBackupNowWithOptions}
          disabled={busy}
          aria-label={`Backup ${instance.name} with options`}
          title="Backup now with options…"
        >
          <Settings2 className="h-3.5 w-3.5" />
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
