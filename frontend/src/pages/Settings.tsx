import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Select, type SelectOption } from "@/components/ui/Select";
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
  const [logging, setLogging] = useState<{ level: string; format: string }>({
    level: "INFO",
    format: "",
  });

  const tzOptions: SelectOption[] = useMemo(
    () => supportedTimezones().map((tz) => ({ value: tz, label: tz })),
    [],
  );
  const tzValues = useMemo(() => new Set(tzOptions.map((o) => o.value)), [tzOptions]);

  // When the stored timezone isn't in the browser's IANA list (older
  // Chromium builds, exotic zones), render an inline text input instead
  // of the dropdown. The "__custom__" entry lets users opt into that
  // mode intentionally.
  const [customTz, setCustomTz] = useState(false);

  useEffect(() => {
    if (settings.data?.backup) setBackup(settings.data.backup);
    if (settings.data?.logging) setLogging(settings.data.logging);
  }, [settings.data]);

  useEffect(() => {
    if (backup.default_timezone && !tzValues.has(backup.default_timezone)) {
      setCustomTz(true);
    }
  }, [backup.default_timezone, tzValues]);

  if (settings.isPending) return <div className="text-sm text-muted-fg">Loading…</div>;

  return (
    <div className="max-w-2xl space-y-8">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <section className="space-y-3">
        <h2 className="text-lg font-medium">Backup file layout</h2>
        <Field label="Filename format">
          <Input
            value={backup.filename_format}
            onChange={(e) => setBackup({ ...backup, filename_format: e.target.value })}
          />
        </Field>
        <Field label="Timestamp format (strftime)">
          <Input
            value={backup.timestamp_format}
            onChange={(e) => setBackup({ ...backup, timestamp_format: e.target.value })}
          />
        </Field>
        <Field label="Directory">
          <Input
            value={backup.directory}
            onChange={(e) => setBackup({ ...backup, directory: e.target.value })}
          />
        </Field>
        <Field label="Default scheduler timezone">
          {customTz ? (
            <div className="space-y-1">
              <Input
                value={backup.default_timezone}
                onChange={(e) =>
                  setBackup({ ...backup, default_timezone: e.target.value })
                }
                placeholder="e.g. America/Los_Angeles"
              />
              <button
                type="button"
                className="text-xs text-accent hover:underline"
                onClick={() => {
                  setCustomTz(false);
                  setBackup({ ...backup, default_timezone: "UTC" });
                }}
              >
                ← pick from the list instead
              </button>
            </div>
          ) : (
            <Select
              value={backup.default_timezone}
              onChange={(v) => {
                if (v === "__custom__") {
                  setCustomTz(true);
                  return;
                }
                setBackup({ ...backup, default_timezone: v });
              }}
              options={tzOptions}
              aria-label="Default scheduler timezone"
              customOption={{ label: "Custom…" }}
            />
          )}
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
            Cap on instances processed concurrently during a full sweep. 1 = serial;
            higher values speed up large fleets at the cost of more simultaneous
            pfSense logins. Default 4.
          </p>
        </Field>
        <div className="flex justify-end">
          <Button onClick={() => updateBackup.mutate(backup)} disabled={updateBackup.isPending}>
            {updateBackup.isPending ? "Saving…" : "Save backup settings"}
          </Button>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-medium">Logging</h2>
        <Field label="Level">
          <Select
            value={logging.level}
            onChange={(v) => setLogging({ ...logging, level: v })}
            options={["DEBUG", "INFO", "WARNING", "ERROR"].map((l) => ({
              value: l,
              label: l,
            }))}
            aria-label="Log level"
          />
        </Field>
        <Field label="Format">
          <Input
            value={logging.format}
            onChange={(e) => setLogging({ ...logging, format: e.target.value })}
          />
        </Field>
        <div className="flex justify-end">
          <Button
            onClick={() => updateLogging.mutate(logging)}
            disabled={updateLogging.isPending}
          >
            {updateLogging.isPending ? "Saving…" : "Save logging settings"}
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
