// WebSocket hook that streams events from /api/events.

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { EventEnvelope } from "./types";

const MAX_EVENTS = 100;

export function useEvents(): {
  events: EventEnvelope[];
  connected: boolean;
} {
  const [events, setEvents] = useState<EventEnvelope[]>([]);
  const [connected, setConnected] = useState(false);
  const qc = useQueryClient();
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let closed = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    // M8: exponential backoff capped at 30s. Resets on a successful open so
    // a brief hiccup doesn't leave us with minute-long retry gaps.
    let attempt = 0;
    const maxDelayMs = 30_000;
    const baseDelayMs = 1_500;

    function connect() {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      const url = `${scheme}://${location.host}/api/events`;
      const ws = new WebSocket(url);
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
      ws.onerror = () => {
        ws.close();
      };
      ws.onmessage = (ev) => {
        try {
          const env = JSON.parse(ev.data) as EventEnvelope;
          setEvents((prev) => {
            const next = [env, ...prev];
            return next.length > MAX_EVENTS ? next.slice(0, MAX_EVENTS) : next;
          });
          // Invalidate relevant queries based on event topic.
          switch (env.topic) {
            case "backup.finished":
            case "backup.failed":
              qc.invalidateQueries({ queryKey: ["backups"] });
              qc.invalidateQueries({ queryKey: ["jobs"] });
              break;
            case "schedule.reloaded":
              qc.invalidateQueries({ queryKey: ["schedule"] });
              qc.invalidateQueries({ queryKey: ["instances"] });
              break;
            case "notification.sent":
              qc.invalidateQueries({ queryKey: ["jobs"] });
              break;
            default:
              break;
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
  }, [qc]);

  return { events, connected };
}
