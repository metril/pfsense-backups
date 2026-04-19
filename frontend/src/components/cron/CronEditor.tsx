// Thin wrapper around <ScheduleForm> that adds the timezone picker and
// the live description + next-runs preview. The heavy lifting (preset
// UI, round-trip parsing) lives in ScheduleForm.

import { useEffect, useMemo, useState } from "react";
import cronstrue from "cronstrue";
import cronParser from "cron-parser";
import { cn } from "@/lib/cn";
import { ScheduleForm } from "./ScheduleForm";

// M12: Intl.supportedValuesOf is widely available in evergreen browsers;
// fall back to a short curated list if missing so the app still works.
function supportedTimezones(): string[] {
  try {
    const fn = (Intl as unknown as { supportedValuesOf?: (k: string) => string[] })
      .supportedValuesOf;
    if (typeof fn === "function") return fn("timeZone");
  } catch {
    // swallow
  }
  return ["UTC", "America/Los_Angeles", "America/New_York", "Europe/London", "Europe/Berlin"];
}

export function CronEditor({
  value,
  onChange,
  timezone = "UTC",
  onTimezoneChange,
}: {
  value: string | null;
  onChange: (v: string | null) => void;
  timezone?: string;
  onTimezoneChange?: (v: string) => void;
}) {
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [nextRuns, setNextRuns] = useState<string[]>([]);
  const tzList = useMemo(supportedTimezones, []);

  useEffect(() => {
    if (!value) {
      setDescription("Disabled");
      setError(null);
      setNextRuns([]);
      return;
    }
    try {
      setDescription(cronstrue.toString(value, { use24HourTimeFormat: true }));
      const it = cronParser.parseExpression(value, { tz: timezone });
      setNextRuns([it.next().toISOString(), it.next().toISOString(), it.next().toISOString()]);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
      setNextRuns([]);
      setDescription("");
    }
  }, [value, timezone]);

  return (
    <div className="space-y-3">
      <ScheduleForm value={value} onChange={onChange} />

      {onTimezoneChange && (
        // Real <select> (not an <input list>) — datalists render unreliably
        // inside portal-rendered modals on some browsers, which made the TZ
        // "dropdown" look stuck.
        <div>
          <label className="block text-xs text-muted-fg" htmlFor="tz-picker">
            Timezone
          </label>
          <select
            id="tz-picker"
            value={tzList.includes(timezone) ? timezone : "__custom__"}
            onChange={(e) => {
              const v = e.target.value;
              if (v !== "__custom__") onTimezoneChange(v);
            }}
            aria-label="Timezone"
            className={cn(
              "mt-1 h-9 w-full rounded-md border border-border bg-bg px-3 text-sm",
              "focus-visible:border-accent focus-visible:outline-none",
            )}
          >
            {/* If the saved tz isn't in the browser's IANA list (e.g. an older
                snapshot), keep it visible as a disabled option so the user
                doesn't silently have it overwritten. */}
            {!tzList.includes(timezone) && (
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

      {error ? (
        <p className="text-xs text-danger">{error}</p>
      ) : (
        <p className="text-xs text-muted-fg">{description}</p>
      )}

      {nextRuns.length > 0 && (
        <ul className="space-y-0.5 text-xs text-muted-fg">
          {nextRuns.map((r) => (
            <li key={r}>Next: {new Date(r).toLocaleString()}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
