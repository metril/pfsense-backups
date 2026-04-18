import { useEffect, useMemo, useState } from "react";
import cronstrue from "cronstrue";
import cronParser from "cron-parser";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { CronBuilderModal } from "./CronBuilderModal";

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
  const [modalOpen, setModalOpen] = useState(false);
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
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value || null)}
          placeholder="0 2 * * *"
          className={cn(error && "border-danger")}
        />
        <Button type="button" variant="secondary" onClick={() => setModalOpen(true)}>
          Build…
        </Button>
      </div>

      {onTimezoneChange && (
        <>
          <Input
            list="pfsense-tz-list"
            value={timezone}
            onChange={(e) => onTimezoneChange(e.target.value)}
            placeholder="UTC"
            aria-label="Timezone"
          />
          {/* Datalist-based suggestions for every IANA tz the browser knows. */}
          <datalist id="pfsense-tz-list">
            {tzList.map((tz) => (
              <option key={tz} value={tz} />
            ))}
          </datalist>
        </>
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

      <CronBuilderModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        onApply={(expr) => {
          onChange(expr);
          setModalOpen(false);
        }}
      />
    </div>
  );
}
