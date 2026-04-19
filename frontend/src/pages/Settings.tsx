import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { cn } from "@/lib/cn";
import { supportedTimezones } from "@/lib/timezones";
import { useSettings, useUpdateBackupSettings, useUpdateLoggingSettings } from "@/api/queries";

export function SettingsPage() {
  const settings = useSettings();
  const updateBackup = useUpdateBackupSettings();
  const updateLogging = useUpdateLoggingSettings();

  const [backup, setBackup] = useState<{
    filename_format: string;
    timestamp_format: string;
    directory: string;
    default_timezone: string;
    backup_all_max_workers: number;
  }>({
    filename_format: "",
    timestamp_format: "",
    directory: "",
    default_timezone: "UTC",
    backup_all_max_workers: 4,
  });
  const [logging, setLogging] = useState<{ level: string; format: string }>({ level: "INFO", format: "" });
  const tzList = useMemo(supportedTimezones, []);

  useEffect(() => {
    if (settings.data?.backup) setBackup(settings.data.backup);
    if (settings.data?.logging) setLogging(settings.data.logging);
  }, [settings.data]);

  if (settings.isPending) return <div className="text-sm text-muted-fg">Loading…</div>;

  return (
    <div className="max-w-2xl space-y-8">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <section className="space-y-3">
        <h2 className="text-lg font-medium">Backup file layout</h2>
        <Field label="Filename format">
          <Input value={backup.filename_format} onChange={(e) => setBackup({ ...backup, filename_format: e.target.value })} />
        </Field>
        <Field label="Timestamp format (strftime)">
          <Input value={backup.timestamp_format} onChange={(e) => setBackup({ ...backup, timestamp_format: e.target.value })} />
        </Field>
        <Field label="Directory">
          <Input value={backup.directory} onChange={(e) => setBackup({ ...backup, directory: e.target.value })} />
        </Field>
        <Field label="Default scheduler timezone">
          <select
            value={tzList.includes(backup.default_timezone) ? backup.default_timezone : "__custom__"}
            onChange={(e) => {
              const v = e.target.value;
              if (v !== "__custom__") setBackup({ ...backup, default_timezone: v });
            }}
            aria-label="Default scheduler timezone"
            className={cn(
              "h-9 w-full rounded-md border border-border bg-bg px-3 text-sm",
              "focus-visible:border-accent focus-visible:outline-none",
            )}
          >
            {!tzList.includes(backup.default_timezone) && (
              <option value="__custom__" disabled>
                {backup.default_timezone} (not in browser list)
              </option>
            )}
            {tzList.map((tz) => (
              <option key={tz} value={tz}>
                {tz}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-muted-fg">
            Used for every instance's schedule unless that instance sets its own override.
            Changing this tells the worker to reload every cron trigger.
          </p>
        </Field>
        <Field label='Parallel backups ("Backup all")'>
          <Input
            type="number"
            min={1}
            max={32}
            value={backup.backup_all_max_workers}
            onChange={(e) =>
              setBackup({
                ...backup,
                backup_all_max_workers: Math.max(
                  1,
                  Math.min(32, Number(e.target.value) || 1),
                ),
              })
            }
          />
          <p className="mt-1 text-xs text-muted-fg">
            Cap on instances processed concurrently during a full sweep.
            1 = serial; higher values speed up large fleets at the cost of
            more simultaneous pfSense logins. Default 4.
          </p>
        </Field>
        <div className="flex justify-end">
          <Button onClick={() => updateBackup.mutate(backup)} disabled={updateBackup.isPending}>
            Save backup settings
          </Button>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-medium">Logging</h2>
        <Field label="Level">
          <select
            value={logging.level}
            onChange={(e) => setLogging({ ...logging, level: e.target.value })}
            className="h-9 w-full rounded-md border border-border bg-bg px-2 text-sm"
          >
            {["DEBUG", "INFO", "WARNING", "ERROR"].map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
        </Field>
        <Field label="Format">
          <Input value={logging.format} onChange={(e) => setLogging({ ...logging, format: e.target.value })} />
        </Field>
        <div className="flex justify-end">
          <Button onClick={() => updateLogging.mutate(logging)} disabled={updateLogging.isPending}>
            Save logging settings
          </Button>
        </div>
      </section>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <Label>{label}</Label>
      <div className="mt-1">{children}</div>
    </div>
  );
}
