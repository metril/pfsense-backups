import {
  cloneElement,
  isValidElement,
  useEffect,
  useId,
  useMemo,
  useState,
} from "react";
import { useBlocker } from "react-router-dom";
import { useForm, useWatch } from "react-hook-form";
import { Button } from "@/components/ui/Button";
import { Label } from "@/components/ui/Label";
import { QueryError } from "@/components/ui/QueryError";
import { type SelectOption } from "@/components/ui/Select";
import { FormInput, FormSelect } from "@/components/ui/form";
import { supportedTimezones } from "@/lib/timezones";
import {
  useSettings,
  useUpdateBackupSettings,
  useUpdateLoggingSettings,
} from "@/api/queries";

type BackupForm = {
  filename_format: string;
  timestamp_format: string;
  directory: string;
  default_timezone: string;
  backup_all_max_workers: number;
};

type LoggingForm = {
  level: string;
  format: string;
};

const BACKUP_DEFAULTS: BackupForm = {
  filename_format: "",
  timestamp_format: "",
  directory: "",
  default_timezone: "UTC",
  backup_all_max_workers: 4,
};

const LOGGING_DEFAULTS: LoggingForm = {
  level: "INFO",
  format: "",
};

export function SettingsPage() {
  const settings = useSettings();
  const updateBackup = useUpdateBackupSettings();
  const updateLogging = useUpdateLoggingSettings();

  const backupForm = useForm<BackupForm>({ defaultValues: BACKUP_DEFAULTS });
  const loggingForm = useForm<LoggingForm>({ defaultValues: LOGGING_DEFAULTS });

  const tzOptions: SelectOption[] = useMemo(
    () => supportedTimezones().map((tz) => ({ value: tz, label: tz })),
    [],
  );
  const tzValues = useMemo(
    () => new Set(tzOptions.map((o) => o.value)),
    [tzOptions],
  );

  // When the stored timezone isn't in the browser's IANA list (older
  // Chromium builds, exotic zones), render an inline text input instead
  // of the dropdown. The "__custom__" entry lets users opt into that
  // mode intentionally.
  const [customTz, setCustomTz] = useState(false);

  // Re-baseline both forms whenever the server data changes; ``reset``
  // also flips ``formState.isDirty`` back to false so save → refetch
  // settles the dirty indicator.
  useEffect(() => {
    if (settings.data?.backup) backupForm.reset(settings.data.backup);
    if (settings.data?.logging) loggingForm.reset(settings.data.logging);
  }, [settings.data, backupForm, loggingForm]);

  const defaultTimezone = useWatch({
    control: backupForm.control,
    name: "default_timezone",
  });

  useEffect(() => {
    if (defaultTimezone && !tzValues.has(defaultTimezone)) {
      setCustomTz(true);
    }
  }, [defaultTimezone, tzValues]);

  const isDirty =
    backupForm.formState.isDirty || loggingForm.formState.isDirty;

  // React Router v6.4+ blocker — fires on in-app navigation. Combined
  // with a ``beforeunload`` for full-page reload / close. ``confirm``
  // is deliberately synchronous so keyboard Enter on the native dialog
  // does the right thing; React Router 7's modal pattern would be a
  // bigger refactor.
  useBlocker(({ currentLocation, nextLocation }) => {
    if (!isDirty) return false;
    if (currentLocation.pathname === nextLocation.pathname) return false;
    return !window.confirm(
      "You have unsaved settings. Leave and discard changes?",
    );
  });
  useEffect(() => {
    if (!isDirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      // Most browsers ignore the custom string since 2019; the empty
      // string + preventDefault still triggers their own "leave site?"
      // dialog which is what we actually want.
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [isDirty]);

  const onSaveBackup = backupForm.handleSubmit((data) =>
    updateBackup.mutate(data),
  );
  const onSaveLogging = loggingForm.handleSubmit((data) =>
    updateLogging.mutate(data),
  );

  if (settings.isPending) return <div className="text-sm text-muted-fg">Loading…</div>;

  // Don't render editable forms seeded with empty defaults when the
  // settings fetch failed — saving them would clobber real values.
  if (settings.isError) {
    return <QueryError title="Could not load settings" error={settings.error} />;
  }

  return (
    <div className="max-w-2xl space-y-8">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <form onSubmit={onSaveBackup} noValidate>
        <section className="space-y-3">
          <h2 className="text-lg font-medium">Backup file layout</h2>
          <Field label="Filename format">
            <FormInput control={backupForm.control} name="filename_format" />
          </Field>
          <Field label="Timestamp format (strftime)">
            <FormInput control={backupForm.control} name="timestamp_format" />
          </Field>
          <Field label="Directory">
            <FormInput control={backupForm.control} name="directory" />
          </Field>
          <Field label="Default scheduler timezone">
            {customTz ? (
              <div className="space-y-1">
                <FormInput
                  control={backupForm.control}
                  name="default_timezone"
                  placeholder="e.g. America/Los_Angeles"
                />
                <button
                  type="button"
                  className="text-xs text-accent hover:underline"
                  onClick={() => {
                    setCustomTz(false);
                    backupForm.setValue("default_timezone", "UTC", {
                      shouldDirty: true,
                    });
                  }}
                >
                  ← pick from the list instead
                </button>
              </div>
            ) : (
              <FormSelect
                control={backupForm.control}
                name="default_timezone"
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
            <FormInput
              control={backupForm.control}
              name="backup_all_max_workers"
              type="number"
              min={1}
              max={32}
              numericFallback={4}
            />
            <p className="mt-1 text-xs text-muted-fg">
              Cap on instances processed concurrently during a full sweep. 1 = serial;
              higher values speed up large fleets at the cost of more simultaneous
              pfSense logins. Default 4.
            </p>
          </Field>
          <div className="flex justify-end">
            <Button type="submit" disabled={updateBackup.isPending}>
              {updateBackup.isPending ? "Saving…" : "Save backup settings"}
            </Button>
          </div>
        </section>
      </form>

      <form onSubmit={onSaveLogging} noValidate>
        <section className="space-y-3">
          <h2 className="text-lg font-medium">Logging</h2>
          <Field label="Level">
            <FormSelect
              control={loggingForm.control}
              name="level"
              options={["DEBUG", "INFO", "WARNING", "ERROR"].map((l) => ({
                value: l,
                label: l,
              }))}
              aria-label="Log level"
            />
          </Field>
          <Field label="Format">
            <FormInput control={loggingForm.control} name="format" />
          </Field>
          <div className="flex justify-end">
            <Button type="submit" disabled={updateLogging.isPending}>
              {updateLogging.isPending ? "Saving…" : "Save logging settings"}
            </Button>
          </div>
        </section>
      </form>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  // See Instances.tsx::Field — same htmlFor+id plumbing so screen
  // readers announce each form control with its visible label.
  const id = useId();
  const controlId = `${id}-control`;
  const labelled = isValidElement(children)
    ? cloneElement(children as React.ReactElement<{ id?: string }>, {
        id: (children.props as { id?: string }).id ?? controlId,
      })
    : children;
  return (
    <div>
      <Label htmlFor={controlId}>{label}</Label>
      <div className="mt-1">{labelled}</div>
    </div>
  );
}
