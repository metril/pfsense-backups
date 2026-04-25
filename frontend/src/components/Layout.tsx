import { Link, NavLink, Outlet } from "react-router-dom";
import {
  Activity,
  BellRing,
  Boxes,
  FileClock,
  History,
  LogOut,
  ScrollText,
  Settings,
  WifiOff,
} from "lucide-react";
import { api } from "@/api/client";
import { useHealth, useMe } from "@/api/queries";
import { useEvents } from "@/api/ws";
import { cn } from "@/lib/cn";
import { EventFeed } from "./EventFeed";

const NAV = [
  { to: "/", label: "Dashboard", icon: Activity, end: true },
  { to: "/instances", label: "Instances", icon: Boxes },
  { to: "/backups", label: "Backups", icon: History },
  { to: "/notifications", label: "Notifications", icon: BellRing },
  { to: "/logs", label: "Logs", icon: ScrollText },
  { to: "/audit", label: "Audit", icon: FileClock },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function Layout() {
  const me = useMe();
  const health = useHealth();
  const { events, connected } = useEvents();

  const workerDown = health.data && !health.data.worker_alive;

  return (
    <div className="flex h-screen">
      <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-muted/40">
        <div className="border-b border-border px-5 py-4">
          <Link to="/" className="text-sm font-semibold tracking-tight">
            pfSense Backup
          </Link>
          <div className="mt-1 text-xs text-muted-fg">
            {connected ? "live" : "reconnecting…"}
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto p-2">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded px-3 py-2 text-sm",
                  isActive ? "bg-accent text-accent-fg" : "text-fg hover:bg-muted",
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-border p-3">
          <div className="mb-2 truncate text-xs text-muted-fg">
            {me.data?.email ?? "loading…"}
          </div>
          <button
            onClick={async () => {
              await api.post("/api/auth/logout");
              window.location.href = "/login";
            }}
            className="flex w-full items-center gap-2 rounded px-2 py-1 text-xs text-muted-fg hover:bg-muted"
          >
            <LogOut className="h-3 w-3" /> Sign out
          </button>
        </div>
      </aside>

      <main className="flex flex-1 min-w-0 flex-col">
        {workerDown && (
          <div className="flex items-center gap-2 border-b border-border bg-danger/20 px-6 py-2 text-sm text-danger">
            <WifiOff className="h-4 w-4" /> Worker is not reachable — scheduled and manual
            backups are paused until it reconnects.
          </div>
        )}
        {/* v0.41.17: the 320px EventFeed track was reserved in the
            grid template unconditionally, so even on narrow viewports
            (where EventFeed itself was ``hidden lg:flex``) the track
            still consumed 320px of horizontal space — squeezing the
            diff view's FIELD/BEFORE/AFTER columns down to char-by-char
            wrapping. The template is now 1-col at ``<lg`` and only
            promotes to the 2-col ``1fr 320px`` layout at ``lg`` and
            up, matching EventFeed's own visibility breakpoint. */}
        <div className="grid flex-1 grid-cols-[1fr] overflow-hidden lg:grid-cols-[1fr_320px]">
          <div className="overflow-y-auto px-8 py-6">
            <Outlet />
          </div>
          <EventFeed events={events} />
        </div>
      </main>
    </div>
  );
}
