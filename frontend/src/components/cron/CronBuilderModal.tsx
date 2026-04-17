import { useEffect, useMemo, useState } from "react";
import cronstrue from "cronstrue";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";

type Mode = "daily" | "hourly" | "weekly" | "monthly" | "custom";

export function CronBuilderModal({
  open,
  onOpenChange,
  onApply,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onApply: (expression: string) => void;
}) {
  const [mode, setMode] = useState<Mode>("daily");
  const [hour, setHour] = useState("2");
  const [minute, setMinute] = useState("0");
  const [weekday, setWeekday] = useState("0"); // Sun=0
  const [day, setDay] = useState("1");
  const [custom, setCustom] = useState("0 2 * * *");

  const expression = useMemo(() => {
    switch (mode) {
      case "daily":
        return `${minute} ${hour} * * *`;
      case "hourly":
        return `${minute} * * * *`;
      case "weekly":
        return `${minute} ${hour} * * ${weekday}`;
      case "monthly":
        return `${minute} ${hour} ${day} * *`;
      default:
        return custom;
    }
  }, [mode, hour, minute, weekday, day, custom]);

  const [description, setDescription] = useState("");
  useEffect(() => {
    try {
      setDescription(cronstrue.toString(expression, { use24HourTimeFormat: true }));
    } catch (e) {
      setDescription((e as Error).message);
    }
  }, [expression]);

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Cron builder"
      description="Assemble a cron expression from presets or paste a custom one."
    >
      <div className="space-y-4">
        <div className="flex flex-wrap gap-2 text-sm">
          {(["daily", "hourly", "weekly", "monthly", "custom"] as Mode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={
                m === mode
                  ? "rounded bg-accent px-3 py-1 text-accent-fg"
                  : "rounded border border-border px-3 py-1 text-fg hover:bg-muted"
              }
            >
              {m}
            </button>
          ))}
        </div>

        {mode !== "custom" && (
          <div className="grid grid-cols-2 gap-3">
            {mode !== "hourly" && (
              <div>
                <Label>Hour (0-23)</Label>
                <Input value={hour} onChange={(e) => setHour(e.target.value)} />
              </div>
            )}
            <div>
              <Label>Minute (0-59)</Label>
              <Input value={minute} onChange={(e) => setMinute(e.target.value)} />
            </div>
            {mode === "weekly" && (
              <div>
                <Label>Weekday (0-6, Sun=0)</Label>
                <Input value={weekday} onChange={(e) => setWeekday(e.target.value)} />
              </div>
            )}
            {mode === "monthly" && (
              <div>
                <Label>Day of month (1-31)</Label>
                <Input value={day} onChange={(e) => setDay(e.target.value)} />
              </div>
            )}
          </div>
        )}

        {mode === "custom" && (
          <div>
            <Label>Cron expression</Label>
            <Input value={custom} onChange={(e) => setCustom(e.target.value)} />
          </div>
        )}

        <div className="rounded border border-border bg-muted/30 p-3 text-sm">
          <div className="font-mono text-accent">{expression}</div>
          <div className="mt-1 text-xs text-muted-fg">{description}</div>
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => onApply(expression)}>Apply</Button>
        </div>
      </div>
    </Dialog>
  );
}
