import { useMemo } from "react";
import { useInstances } from "@/api/queries";
import { cn } from "@/lib/cn";
import type { EventEnvelope } from "@/api/types";

type NameLookup = (id: number | null | undefined) => string;

function format(event: EventEnvelope, nameOf: NameLookup): { line: string; tone: string } {
  switch (event.topic) {
    case "backup.started":
      // ``instance_name`` is on the wire for this event. Still route through
      // nameOf so the tone logic doesn't bother resolving separately.
      return { line: `${event.instance_name} — backup started`, tone: "text-accent" };
    case "backup.progress":
      return { line: `${nameOf(event.instance_id)} — ${event.phase}`, tone: "text-muted-fg" };
    case "backup.finished":
      return {
        line: `${nameOf(event.instance_id)} — backup ${event.success ? "ok" : "fail"} (${event.duration_seconds.toFixed(1)}s, ${event.size_bytes}B)`,
        tone: event.success ? "text-ok" : "text-danger",
      };
    case "backup.failed":
      return { line: `${nameOf(event.instance_id)} — failed: ${event.error}`, tone: "text-danger" };
    case "schedule.reloaded":
      return {
        line: `schedule reloaded${event.instance_id ? ` (${nameOf(event.instance_id)})` : ""}`,
        tone: "text-muted-fg",
      };
    case "test_connection.result":
      return {
        line: `${nameOf(event.instance_id)} — test ${event.ok ? "ok" : "fail"}${event.detail ? `: ${event.detail}` : ""}`,
        tone: event.ok ? "text-ok" : "text-danger",
      };
    case "notification.sent":
      return {
        line: `notification ${event.notification_id} — ${event.success ? "sent" : "failed"}`,
        tone: event.success ? "text-ok" : "text-danger",
      };
    case "worker.heartbeat":
      return { line: "heartbeat", tone: "text-muted-fg" };
  }
}

export function EventFeed({ events }: { events: EventEnvelope[] }) {
  const instances = useInstances();
  const nameOf = useMemo<NameLookup>(() => {
    const byId = new Map<number, string>();
    for (const i of instances.data ?? []) byId.set(i.id, i.name);
    return (id) => (id == null ? "" : byId.get(id) ?? `id=${id}`);
  }, [instances.data]);

  return (
    <aside className="hidden flex-col border-l border-border bg-muted/40 lg:flex">
      <div className="border-b border-border px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-fg">
        Events
      </div>
      <div className="flex-1 overflow-y-auto p-3 font-mono text-xs">
        {events.length === 0 && (
          <div className="text-muted-fg">Waiting for worker events…</div>
        )}
        {events
          .filter((e) => e.topic !== "worker.heartbeat")
          .map((e, i) => {
            const { line, tone } = format(e, nameOf);
            return (
              <div key={i} className="flex gap-2 py-1">
                <span className="text-muted-fg">{e.ts.substring(11, 19)}</span>
                <span className={cn("flex-1", tone)}>{line}</span>
              </div>
            );
          })}
      </div>
    </aside>
  );
}
