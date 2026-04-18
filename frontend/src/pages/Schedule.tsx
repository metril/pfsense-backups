import { useEffect, useState } from "react";
import { useSchedules, useUpdateSchedule } from "@/api/queries";
import { CronEditor } from "@/components/cron/CronEditor";
import { Button } from "@/components/ui/Button";
import { Label } from "@/components/ui/Label";

export function SchedulePage() {
  const { data, isPending } = useSchedules();
  const update = useUpdateSchedule();

  return (
    <div>
      <h1 className="text-2xl font-semibold">Schedules</h1>
      <p className="mt-1 text-sm text-muted-fg">
        Each instance runs on its own cron. Leave blank to disable scheduling for that instance.
      </p>

      {isPending ? (
        <div className="mt-6 text-sm text-muted-fg">Loading…</div>
      ) : (
        <div className="mt-6 space-y-4">
          {data!.map((row) => (
            <Card key={row.instance_id} row={row} onSave={(patch) => update.mutate(patch)} />
          ))}
          {data!.length === 0 && (
            <div className="text-sm text-muted-fg">No instances configured.</div>
          )}
        </div>
      )}
    </div>
  );
}

function Card({
  row,
  onSave,
}: {
  row: {
    instance_id: number;
    instance_name: string;
    cron_expression: string | null;
    cron_timezone: string;
    enabled: boolean;
  };
  onSave: (patch: { id: number; cron_expression: string | null; cron_timezone: string; enabled: boolean }) => void;
}) {
  const [cron, setCron] = useState(row.cron_expression);
  const [tz, setTz] = useState(row.cron_timezone);
  const [enabled, setEnabled] = useState(row.enabled);

  useEffect(() => setCron(row.cron_expression), [row.cron_expression]);
  useEffect(() => setTz(row.cron_timezone), [row.cron_timezone]);
  useEffect(() => setEnabled(row.enabled), [row.enabled]);

  const dirty = cron !== row.cron_expression || tz !== row.cron_timezone || enabled !== row.enabled;

  return (
    <div className="rounded-lg border border-border bg-muted/20 p-4">
      <div className="flex items-center justify-between">
        <div className="font-medium">{row.instance_name}</div>
        <label className="flex items-center gap-2 text-xs text-muted-fg">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          enabled
        </label>
      </div>
      <div className="mt-3">
        <Label>Cron</Label>
        <CronEditor value={cron} onChange={setCron} timezone={tz} onTimezoneChange={setTz} />
        {/* M14: blank cron == disabled; spell it out so users don't assume
            the 'enabled' switch runs without a schedule. */}
        <p className="mt-1 text-xs text-muted-fg">
          Leave the cron field blank to disable scheduling for this instance.
        </p>
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <Button
          size="sm"
          disabled={!dirty}
          onClick={() =>
            onSave({ id: row.instance_id, cron_expression: cron, cron_timezone: tz, enabled })
          }
        >
          Save
        </Button>
      </div>
    </div>
  );
}
