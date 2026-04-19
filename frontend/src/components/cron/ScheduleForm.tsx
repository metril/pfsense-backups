// Preset-first schedule editor. Emits a 5-field cron string (or null
// when disabled) so the caller doesn't need to know we modelled things
// as presets internally. Round-trips an existing cron back into the
// matching preset so reopening an instance restores the same controls
// the user picked last time.

import { useMemo, useState } from "react";
import { cn } from "@/lib/cn";
import { Input } from "@/components/ui/Input";

export type Preset =
  | "daily"
  | "hourly"
  | "weekdays"
  | "weekly"
  | "monthly"
  | "advanced";

type DomDay = number | "last";

interface FormState {
  preset: Preset;
  hour: number;      // 0..23
  minute: number;    // 0..59
  everyHours: number; // 1..23 (hourly preset)
  days: number[];    // 1..7 (ISO; Mon=1, Sun=7) for weekly preset
  domDay: DomDay;    // monthly preset
  raw: string;       // advanced preset
}

const DEFAULT_STATE: FormState = {
  preset: "daily",
  hour: 2,
  minute: 0,
  everyHours: 1,
  days: [1, 2, 3, 4, 5],
  domDay: 1,
  raw: "",
};

const DOW_LABELS: { n: number; short: string }[] = [
  { n: 1, short: "Mon" },
  { n: 2, short: "Tue" },
  { n: 3, short: "Wed" },
  { n: 4, short: "Thu" },
  { n: 5, short: "Fri" },
  { n: 6, short: "Sat" },
  { n: 7, short: "Sun" },
];

const HOURLY_OPTIONS = [1, 2, 3, 4, 6, 8, 12];

const PRESETS: { id: Preset; label: string }[] = [
  { id: "daily", label: "Daily" },
  { id: "hourly", label: "Hourly" },
  { id: "weekdays", label: "Weekdays" },
  { id: "weekly", label: "Weekly" },
  { id: "monthly", label: "Monthly" },
  { id: "advanced", label: "Advanced" },
];

// -------- classify + emit --------

export function classify(cron: string | null): FormState {
  if (!cron) return DEFAULT_STATE;
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) {
    return { ...DEFAULT_STATE, preset: "advanced", raw: cron };
  }
  const [mm, hh, dom, mon, dow] = parts;
  const isInt = (s: string) => /^\d+$/.test(s);
  const mNum = Number(mm);
  const hNum = Number(hh);
  const minuteOk = isInt(mm) && mNum >= 0 && mNum <= 59;
  const hourOk = isInt(hh) && hNum >= 0 && hNum <= 23;

  // daily: MM HH * * *
  if (minuteOk && hourOk && dom === "*" && mon === "*" && dow === "*") {
    return { ...DEFAULT_STATE, preset: "daily", minute: mNum, hour: hNum };
  }

  // hourly: MM * * * *   OR   MM */N * * *
  if (minuteOk && mon === "*" && dom === "*" && dow === "*") {
    if (hh === "*") {
      return { ...DEFAULT_STATE, preset: "hourly", minute: mNum, everyHours: 1 };
    }
    const step = hh.match(/^\*\/(\d+)$/);
    if (step) {
      const n = Number(step[1]);
      if (n >= 1 && n <= 23) {
        return { ...DEFAULT_STATE, preset: "hourly", minute: mNum, everyHours: n };
      }
    }
  }

  // weekdays: MM HH * * 1-5
  if (minuteOk && hourOk && dom === "*" && mon === "*" && dow === "1-5") {
    return { ...DEFAULT_STATE, preset: "weekdays", minute: mNum, hour: hNum };
  }

  // weekly: MM HH * * <csv of single ints in 0..7>
  if (minuteOk && hourOk && dom === "*" && mon === "*") {
    const days = parseDowCsv(dow);
    if (days) {
      return {
        ...DEFAULT_STATE, preset: "weekly", minute: mNum, hour: hNum, days,
      };
    }
  }

  // monthly: MM HH <D or L> * *
  if (minuteOk && hourOk && mon === "*" && dow === "*") {
    if (dom === "L") {
      return {
        ...DEFAULT_STATE, preset: "monthly", minute: mNum, hour: hNum, domDay: "last",
      };
    }
    if (isInt(dom)) {
      const d = Number(dom);
      if (d >= 1 && d <= 31) {
        return {
          ...DEFAULT_STATE, preset: "monthly", minute: mNum, hour: hNum, domDay: d,
        };
      }
    }
  }

  return { ...DEFAULT_STATE, preset: "advanced", raw: cron };
}

function parseDowCsv(csv: string): number[] | null {
  const parts = csv.split(",");
  if (parts.length === 0) return null;
  const set = new Set<number>();
  for (const p of parts) {
    if (!/^\d+$/.test(p)) return null;
    const n = Number(p);
    if (n < 0 || n > 7) return null;
    // cron accepts 0 or 7 for Sunday; normalize to 7 so display is stable.
    set.add(n === 0 ? 7 : n);
  }
  if (set.size === 0) return null;
  return [...set].sort((a, b) => a - b);
}

function toCron(s: FormState): string {
  const mm = String(s.minute);
  const hh = String(s.hour);
  switch (s.preset) {
    case "daily":
      return `${mm} ${hh} * * *`;
    case "hourly":
      return s.everyHours === 1
        ? `${mm} * * * *`
        : `${mm} */${s.everyHours} * * *`;
    case "weekdays":
      return `${mm} ${hh} * * 1-5`;
    case "weekly": {
      const days = s.days.length > 0 ? [...s.days].sort((a, b) => a - b) : [1];
      return `${mm} ${hh} * * ${days.join(",")}`;
    }
    case "monthly":
      return `${mm} ${hh} ${s.domDay === "last" ? "L" : s.domDay} * *`;
    default:
      return s.raw;
  }
}

// -------- component --------

export function ScheduleForm({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (v: string | null) => void;
}) {
  // EditorDialog remounts ScheduleForm on each instance edit (keyed by id),
  // so classifying once on mount is enough — we own the local state from
  // there and every change flows back out via `onChange`.
  const [state, setState] = useState<FormState>(() => classify(value));
  // Remember the last non-null cron so Enable→OFF→ON restores it instead of
  // resetting to defaults.
  const [stashed, setStashed] = useState<string>(value ?? toCron(classify(value)));

  const enabled = value !== null;

  function emit(next: FormState) {
    setState(next);
    const cron = toCron(next);
    setStashed(cron);
    onChange(cron);
  }

  function toggleEnabled(on: boolean) {
    if (on) {
      onChange(stashed);
    } else {
      // Keep `state` as-is so the UI stays populated; just tell the parent
      // to store null on the wire.
      onChange(null);
    }
  }

  const timeStr = useMemo(
    () => `${String(state.hour).padStart(2, "0")}:${String(state.minute).padStart(2, "0")}`,
    [state.hour, state.minute],
  );

  function onTimeChange(v: string) {
    const [h, m] = v.split(":").map(Number);
    if (!Number.isFinite(h) || !Number.isFinite(m)) return;
    emit({ ...state, hour: h, minute: m });
  }

  return (
    <div className="space-y-3">
      {/* Enable toggle */}
      <label className="inline-flex items-center gap-2 text-sm">
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          aria-label="Enable backup schedule"
          onClick={() => toggleEnabled(!enabled)}
          className={cn(
            "inline-flex h-5 w-9 items-center rounded-full transition-colors",
            enabled ? "bg-accent" : "bg-muted",
          )}
        >
          <span
            className={cn(
              "inline-block h-4 w-4 transform rounded-full bg-fg transition-transform",
              enabled ? "translate-x-4" : "translate-x-0.5",
            )}
          />
        </button>
        <span>Run on a schedule</span>
      </label>

      {enabled && (
        <>
          <div className="flex flex-wrap gap-1.5">
            {PRESETS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => emit({ ...state, preset: p.id })}
                className={cn(
                  "rounded-full px-3 py-1 text-xs",
                  state.preset === p.id
                    ? "bg-accent text-accent-fg"
                    : "border border-border text-fg hover:bg-muted",
                )}
              >
                {p.label}
              </button>
            ))}
          </div>

          {state.preset === "daily" && (
            <TimeRow time={timeStr} onChange={onTimeChange} />
          )}

          {state.preset === "hourly" && (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted-fg">Every</span>
              <select
                value={state.everyHours}
                onChange={(e) =>
                  emit({ ...state, everyHours: Number(e.target.value) })
                }
                className="h-9 rounded-md border border-border bg-bg px-2 text-sm"
                aria-label="Hours between runs"
              >
                {HOURLY_OPTIONS.map((n) => (
                  <option key={n} value={n}>{n === 1 ? "hour" : `${n} hours`}</option>
                ))}
              </select>
              <span className="text-muted-fg">at minute</span>
              <select
                value={state.minute}
                onChange={(e) => emit({ ...state, minute: Number(e.target.value) })}
                className="h-9 rounded-md border border-border bg-bg px-2 text-sm"
                aria-label="Minute of the hour"
              >
                {[0, 15, 30, 45].map((m) => (
                  <option key={m} value={m}>:{String(m).padStart(2, "0")}</option>
                ))}
              </select>
            </div>
          )}

          {state.preset === "weekdays" && (
            <TimeRow time={timeStr} onChange={onTimeChange} />
          )}

          {state.preset === "weekly" && (
            <div className="space-y-2">
              <div className="flex flex-wrap gap-1.5">
                {DOW_LABELS.map(({ n, short }) => {
                  const active = state.days.includes(n);
                  return (
                    <button
                      key={n}
                      type="button"
                      onClick={() => {
                        const nextDays = active
                          ? state.days.filter((d) => d !== n)
                          : [...state.days, n];
                        // At least one day must remain; ignore clicks that
                        // would empty the set.
                        if (nextDays.length === 0) return;
                        emit({ ...state, days: nextDays });
                      }}
                      className={cn(
                        // w-12 + text-center keeps every pill the same width
                        // regardless of Mon vs Wed vs Fri etc., so the row
                        // reads as a single segmented control.
                        "w-12 rounded-md py-1 text-center text-xs tabular-nums",
                        active
                          ? "bg-accent text-accent-fg"
                          : "border border-border text-fg hover:bg-muted",
                      )}
                      aria-pressed={active}
                    >
                      {short}
                    </button>
                  );
                })}
              </div>
              <TimeRow time={timeStr} onChange={onTimeChange} />
            </div>
          )}

          {state.preset === "monthly" && (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted-fg">On day</span>
              <select
                value={state.domDay === "last" ? "L" : String(state.domDay)}
                onChange={(e) =>
                  emit({
                    ...state,
                    domDay: e.target.value === "L" ? "last" : Number(e.target.value),
                  })
                }
                className="h-9 rounded-md border border-border bg-bg px-2 text-sm"
                aria-label="Day of the month"
              >
                {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
                <option value="L">Last</option>
              </select>
              <TimeRow time={timeStr} onChange={onTimeChange} inline />
            </div>
          )}

          {state.preset === "advanced" && (
            <div>
              <Input
                value={state.raw}
                onChange={(e) => emit({ ...state, raw: e.target.value })}
                placeholder="0 2 * * *"
                aria-label="Cron expression"
              />
              <p className="mt-1 text-xs text-muted-fg">
                Raw 5-field cron (minute hour day-of-month month day-of-week).
                Use the presets above for the common cases.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function TimeRow({
  time,
  onChange,
  inline = false,
}: {
  time: string;
  onChange: (v: string) => void;
  inline?: boolean;
}) {
  return (
    <div className={inline ? "inline-flex items-center gap-2" : "flex items-center gap-2"}>
      <span className="text-sm text-muted-fg">At</span>
      <input
        type="time"
        value={time}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 rounded-md border border-border bg-bg px-2 text-sm"
        aria-label="Time of day"
      />
    </div>
  );
}
