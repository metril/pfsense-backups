import { useEffect, useMemo, useRef, useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { Pause, Play, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { FormInput } from "@/components/ui/form";
import { cn } from "@/lib/cn";

const MAX_LINES = 1000;

type Service = "web" | "worker";
type Level = "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";

interface LogEntry {
  ts: string;
  service: Service;
  level: Level;
  logger: string;
  message: string;
}

type WsFrame =
  | { type: "snapshot"; entries: LogEntry[] }
  | { type: "log"; entry: LogEntry };

// Client-side levels are ordered so users can pick a minimum level to show.
const LEVEL_ORDER: Record<Level, number> = {
  DEBUG: 10,
  INFO: 20,
  WARNING: 30,
  ERROR: 40,
  CRITICAL: 50,
};

// Level → text/row styling. Uses theme tokens so colors match Toast/Badge
// elsewhere in the app instead of stock Tailwind palette values.
const LEVEL_TEXT: Record<Level, string> = {
  DEBUG: "text-muted-fg",
  INFO: "text-info",
  WARNING: "text-warn",
  ERROR: "text-danger",
  CRITICAL: "text-danger font-semibold",
};

const LEVEL_ROW: Record<Level, string> = {
  DEBUG: "",
  INFO: "",
  WARNING: "bg-warn/5",
  ERROR: "bg-danger/10",
  CRITICAL: "bg-danger/20",
};

const SERVICE_TONE: Record<Service, string> = {
  web: "text-accent",
  worker: "text-ok",
};

type LogsFilterForm = {
  serviceFilter: Service | "all";
  minLevel: Level;
  loggerFilter: string;
  search: string;
};

const LOGS_FILTER_DEFAULTS: LogsFilterForm = {
  serviceFilter: "all",
  minLevel: "DEBUG",
  loggerFilter: "",
  search: "",
};

export function LogsPage() {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const { control } = useForm<LogsFilterForm>({
    defaultValues: LOGS_FILTER_DEFAULTS,
  });
  const serviceFilter = useWatch({ control, name: "serviceFilter" });
  const minLevel = useWatch({ control, name: "minLevel" });
  const loggerFilter = useWatch({ control, name: "loggerFilter" });
  const search = useWatch({ control, name: "search" });
  const [autoScroll, setAutoScroll] = useState(true);

  const bottomRef = useRef<HTMLDivElement>(null);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let closed = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    const baseDelayMs = 1_000;
    const maxDelayMs = 30_000;

    function connect() {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${scheme}://${location.host}/api/logs/ws`);
      socketRef.current = ws;

      ws.onopen = () => {
        attempt = 0;
        setConnected(true);
      };
      ws.onclose = () => {
        setConnected(false);
        if (!closed) {
          const delay = Math.min(maxDelayMs, baseDelayMs * 2 ** attempt);
          attempt += 1;
          reconnectTimer = setTimeout(connect, delay);
        }
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (ev) => {
        try {
          const frame = JSON.parse(ev.data) as WsFrame;
          if (frame.type === "snapshot") {
            setEntries(frame.entries.slice(-MAX_LINES));
          } else {
            setEntries((prev) => {
              const next = [...prev, frame.entry];
              return next.length > MAX_LINES ? next.slice(-MAX_LINES) : next;
            });
          }
        } catch {
          // ignore malformed frame
        }
      };
    }

    connect();
    return () => {
      closed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socketRef.current?.close();
    };
  }, []);

  const loggerNames = useMemo(() => {
    const s = new Set<string>();
    for (const e of entries) s.add(e.logger);
    return Array.from(s).sort();
  }, [entries]);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const min = LEVEL_ORDER[minLevel];
    return entries.filter((e) => {
      if (serviceFilter !== "all" && e.service !== serviceFilter) return false;
      if (LEVEL_ORDER[e.level] < min) return false;
      if (loggerFilter && e.logger !== loggerFilter) return false;
      if (needle && !e.message.toLowerCase().includes(needle)) return false;
      return true;
    });
  }, [entries, serviceFilter, minLevel, loggerFilter, search]);

  useEffect(() => {
    if (!autoScroll) return;
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [filtered, autoScroll]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Logs</h1>
        {/* Announce WebSocket connection transitions to assistive
            tech. ``role="status"`` gives screen readers the polite
            live region; the dot itself stays ``aria-hidden`` because
            the text next to it ("live" / "reconnecting…") already
            conveys the state. */}
        <div
          role="status"
          aria-live="polite"
          className="flex items-center gap-2 text-xs text-muted-fg"
        >
          <span
            className={cn(
              "inline-block h-2 w-2 rounded-full",
              connected ? "bg-emerald-500" : "bg-muted",
            )}
            aria-hidden
          />
          {connected ? "live" : "reconnecting…"}
          <span aria-hidden>·</span>
          <span>
            {filtered.length} / {entries.length} lines
          </span>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-[auto_auto_auto_1fr_auto_auto] gap-2">
        <Controller
          control={control}
          name="serviceFilter"
          render={({ field }) => (
            <select
              value={field.value}
              onChange={field.onChange}
              className="h-9 rounded-md border border-border bg-bg px-2 text-sm"
              aria-label="Service filter"
            >
              <option value="all">All services</option>
              <option value="web">web</option>
              <option value="worker">worker</option>
            </select>
          )}
        />

        <Controller
          control={control}
          name="minLevel"
          render={({ field }) => (
            <select
              value={field.value}
              onChange={field.onChange}
              className="h-9 rounded-md border border-border bg-bg px-2 text-sm"
              aria-label="Minimum level"
            >
              <option value="DEBUG">DEBUG+</option>
              <option value="INFO">INFO+</option>
              <option value="WARNING">WARNING+</option>
              <option value="ERROR">ERROR+</option>
              <option value="CRITICAL">CRITICAL only</option>
            </select>
          )}
        />

        <Controller
          control={control}
          name="loggerFilter"
          render={({ field }) => (
            <select
              value={field.value}
              onChange={field.onChange}
              className="h-9 rounded-md border border-border bg-bg px-2 text-sm max-w-56"
              aria-label="Logger filter"
            >
              <option value="">All loggers</option>
              {loggerNames.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          )}
        />

        <FormInput
          control={control}
          name="search"
          placeholder="Search message…"
          aria-label="Search message text"
        />

        <Button
          type="button"
          variant="secondary"
          onClick={() => setAutoScroll((v) => !v)}
          aria-pressed={autoScroll}
          title={autoScroll ? "Pause auto-scroll" : "Resume auto-scroll"}
        >
          {autoScroll ? (
            <>
              <Pause className="h-4 w-4" /> Pause
            </>
          ) : (
            <>
              <Play className="h-4 w-4" /> Follow
            </>
          )}
        </Button>

        <Button
          type="button"
          variant="ghost"
          onClick={() => setEntries([])}
          title="Clear visible buffer (does not clear server-side)"
        >
          <Trash2 className="h-4 w-4" /> Clear
        </Button>
      </div>

      <div className="mt-4 flex-1 min-h-0 overflow-y-auto rounded-md border border-border bg-bg font-mono text-xs">
        {filtered.length === 0 ? (
          <div className="p-6 text-center text-muted-fg">
            {entries.length === 0
              ? connected
                ? "Waiting for log output…"
                : "Connecting…"
              : "No lines match the current filters."}
          </div>
        ) : (
          <ul className="divide-y divide-border/40">
            {filtered.map((e, i) => (
              <li
                key={`${e.ts}-${i}`}
                className={cn(
                  "flex gap-3 px-3 py-1 whitespace-pre-wrap break-words",
                  LEVEL_ROW[e.level],
                )}
              >
                <span className="shrink-0 text-muted-fg tabular-nums">
                  {e.ts.replace("T", " ").slice(0, 19)}
                </span>
                <span className={cn("shrink-0 w-14 font-semibold", SERVICE_TONE[e.service])}>
                  {e.service}
                </span>
                <span className={cn("shrink-0 w-16", LEVEL_TEXT[e.level])}>
                  {e.level}
                </span>
                <span className="shrink-0 max-w-[18rem] truncate text-muted-fg">
                  {e.logger}
                </span>
                <span className={cn("flex-1", LEVEL_TEXT[e.level])}>{e.message}</span>
              </li>
            ))}
          </ul>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
