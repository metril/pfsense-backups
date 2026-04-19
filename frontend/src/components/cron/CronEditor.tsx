// Thin wrapper around <ScheduleForm> that adds the timezone picker and
// the live description + next-runs preview. The heavy lifting (preset
// UI, round-trip parsing) lives in ScheduleForm.

import { useEffect, useMemo, useState } from "react";
import cronstrue from "cronstrue";
import cronParser from "cron-parser";
import { cn } from "@/lib/cn";
import { supportedTimezones } from "@/lib/timezones";
import { ScheduleForm } from "./ScheduleForm";

export function CronEditor({
  value,
  onChange,
  timezone,
  globalTimezone,
  onTimezoneChange,
}: {
  value: string | null;
  onChange: (v: string | null) => void;
  /** Per-instance override. null = inherit globalTimezone. */
  timezone: string | null;
  /** Global default from BackupSettings.default_timezone. */
  globalTimezone: string;
  /** Pass null to clear the per-instance override back to "inherit". */
  onTimezoneChange?: (v: string | null) => void;
}) {
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [nextRuns, setNextRuns] = useState<string[]>([]);
  const tzList = useMemo(supportedTimezones, []);

  const effectiveTz = timezone ?? globalTimezone;

  useEffect(() => {
    if (!value) {
      setDescription("Disabled");
      setError(null);
      setNextRuns([]);
      return;
    }
    try {
      setDescription(cronstrue.toString(value, { use24HourTimeFormat: true }));
      const it = cronParser.parseExpression(value, { tz: effectiveTz });
      setNextRuns([it.next().toISOString(), it.next().toISOString(), it.next().toISOString()]);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
      setNextRuns([]);
      setDescription("");
    }
  }, [value, effectiveTz]);

  const overrideActive = timezone != null;

  return (
    <div className="space-y-3">
      <ScheduleForm value={value} onChange={onChange} />

      {/* Timezone only makes sense when a schedule is actually running. */}
      {value !== null && onTimezoneChange && (
        <div className="space-y-2">
          {!overrideActive ? (
            // Inheriting the global default — show a compact summary line
            // with a link to reveal the picker. Keeps the editor uncluttered
            // for the 95% case.
            <div className="text-xs">
              <span className="text-muted-fg">Runs in </span>
              <span className="font-mono">{globalTimezone}</span>
              <span className="text-muted-fg"> (global default)</span>
              <button
                type="button"
                onClick={() => onTimezoneChange(globalTimezone)}
                className="ml-2 text-accent hover:underline"
              >
                Use a different timezone for this instance →
              </button>
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between">
                <label className="text-xs text-muted-fg" htmlFor="tz-picker">
                  Timezone override
                </label>
                <button
                  type="button"
                  onClick={() => onTimezoneChange(null)}
                  className="text-xs text-muted-fg hover:text-accent"
                  title="Clear override and inherit the global default"
                >
                  Use global ({globalTimezone})
                </button>
              </div>
              <select
                id="tz-picker"
                value={tzList.includes(timezone!) ? timezone! : "__custom__"}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v !== "__custom__") onTimezoneChange(v);
                }}
                aria-label="Timezone override"
                className={cn(
                  "mt-1 h-9 w-full rounded-md border border-border bg-bg px-3 text-sm",
                  "focus-visible:border-accent focus-visible:outline-none",
                )}
              >
                {!tzList.includes(timezone!) && (
                  <option value="__custom__" disabled>
                    {timezone} (not in browser list)
                  </option>
                )}
                {tzList.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      )}

      {value !== null && (error ? (
        <p className="text-xs text-danger">{error}</p>
      ) : (
        <p className="text-xs text-muted-fg">{description}</p>
      ))}

      {value !== null && nextRuns.length > 0 && (
        <ul className="space-y-0.5 text-xs text-muted-fg">
          {nextRuns.map((r) => (
            <li key={r}>Next: {new Date(r).toLocaleString()}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
