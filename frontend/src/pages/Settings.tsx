import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { useSettings, useUpdateBackupSettings, useUpdateLoggingSettings } from "@/api/queries";

export function SettingsPage() {
  const settings = useSettings();
  const updateBackup = useUpdateBackupSettings();
  const updateLogging = useUpdateLoggingSettings();

  const [backup, setBackup] = useState<{ filename_format: string; timestamp_format: string; directory: string }>(
    { filename_format: "", timestamp_format: "", directory: "" },
  );
  const [logging, setLogging] = useState<{ level: string; format: string }>({ level: "INFO", format: "" });

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
