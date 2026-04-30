import { useState } from "react";
import { Link } from "react-router-dom";
import { Play, PlayCircle, Plug, Server } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonRows } from "@/components/ui/Skeleton";
import { SplitButton } from "@/components/ui/SplitButton";
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
import { formatLocal } from "@/lib/datetime";

export function Dashboard() {
  const instances = useInstances();
  const schedules = useSchedules();
  const backups = useBackups();

  const backupNow = useBackupNow();
  const backupAll = useBackupAll();
  const test = useTestConnection();

  // Which dialog is open: "all" (top-bar), a number = instance id, or null.
  const [overridesOpen, setOverridesOpen] = useState<"all" | number | null>(null);

  if (instances.error) {
    return <div className="text-sm text-danger">Failed to load instances.</div>;
  }

  const loading = instances.isPending;
  const rows = instances.data ?? [];
  const disabled = backupAll.isPending || rows.length === 0 || loading;
  const byId = new Map(schedules.data?.map((s) => [s.instance_id, s]) ?? []);

  return (
    <div>
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <div className="flex items-center gap-4">
          <SplitButton
            primaryLabel={backupAll.isPending ? "Starting…" : "Backup all"}
            primaryIcon={<PlayCircle className="h-4 w-4" />}
            onPrimary={() => backupAll.mutate(undefined)}
            disabled={disabled}
            size="sm"
            menu={[
              {
                label: "Backup all with options…",
                onSelect: () => setOverridesOpen("all"),
              },
            ]}
          />
          <Link to="/instances" className="text-sm text-accent hover:underline">
            Manage instances →
          </Link>
        </div>
      </div>

      {overridesOpen !== null && (
        <BackupOverridesDialog
          key={String(overridesOpen)}
          title={
            overridesOpen === "all"
              ? "Backup all with options"
              : `Backup ${rows.find((i) => i.id === overridesOpen)?.name ?? ""} with options`
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

      {loading && (
        <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <SkeletonRows key={i} count={4} />
          ))}
        </div>
      )}

      {!loading && rows.length === 0 && (
        <div className="mt-8">
          <EmptyState
            icon={<Server className="h-8 w-8" />}
            headline="No pfSense instances configured yet"
            body="Add your first instance from the Instances page — once it's set up you can back it up manually or on a schedule."
            cta={
              <Link
                to="/instances"
                className="inline-flex h-8 items-center rounded-md bg-accent px-3 text-sm font-medium text-accent-fg hover:bg-accent/90"
              >
                Go to Instances
              </Link>
            }
          />
        </div>
      )}

      {!loading && rows.length > 0 && (
        <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {rows.map((inst) => (
            <Tile
              key={inst.id}
              instance={inst}
              schedule={byId.get(inst.id)}
              lastBackup={backups.data?.find((b) => b.instance_id === inst.id)}
              onBackupNow={() => backupNow.mutate({ id: inst.id })}
              onBackupNowWithOptions={() => setOverridesOpen(inst.id)}
              onTest={() => test.mutate(inst.id)}
              // Per-instance busy flag. TanStack Query exposes the last
              // mutation's `variables`; compare to this tile's id so clicking
              // one tile doesn't freeze every tile's buttons.
              busy={
                (backupNow.isPending && backupNow.variables?.id === inst.id) ||
                (test.isPending && test.variables === inst.id)
              }
            />
          ))}
        </div>
      )}
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
        <div className="min-w-0">
          <Link
            to={`/instances/${instance.id}`}
            className="truncate text-base font-semibold hover:text-accent"
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
              {formatLocal(lastBackup.started_at)} ·{" "}
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

      <div className="mt-4 flex flex-wrap gap-2">
        <SplitButton
          primaryLabel="Backup Now"
          primaryIcon={<Play className="h-3.5 w-3.5" />}
          onPrimary={onBackupNow}
          disabled={busy}
          size="sm"
          menu={[
            {
              label: "Backup now with options…",
              onSelect: onBackupNowWithOptions,
            },
          ]}
        />
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
