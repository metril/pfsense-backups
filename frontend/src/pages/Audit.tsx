import { Fragment, useState } from "react";
import { ChevronDown, ChevronRight, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { formatLocal } from "@/lib/datetime";
import { useAuditFacets, useAuditLog, type AuditFilter } from "@/api/queries";

const ACTION_TONE: Record<string, string> = {
  create: "text-ok",
  update: "text-info",
  delete: "text-danger",
  trigger: "text-accent",
};

function boundary(d: string, end: boolean): string | undefined {
  if (!d) return undefined;
  const [y, m, dd] = d.split("-").map(Number);
  if (!y || !m || !dd) return undefined;
  const date = new Date(
    y, m - 1, dd,
    end ? 23 : 0, end ? 59 : 0, end ? 59 : 0, end ? 999 : 0,
  );
  return date.toISOString();
}

export function AuditPage() {
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [resource, setResource] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const filter: AuditFilter = {
    actor: actor || undefined,
    action: action || undefined,
    resource: resource || undefined,
    tsFrom: boundary(fromDate, false),
    tsTo: boundary(toDate, true),
    limit: 500,
  };

  const facets = useAuditFacets();
  const entries = useAuditLog(filter);

  const hasFilter = Boolean(actor || action || resource || fromDate || toDate);

  function toggle(id: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Audit log</h1>
        <div className="text-xs text-muted-fg">
          {entries.isPending ? "Loading…" : `${entries.data?.length ?? 0} entries`}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <select
          value={actor}
          onChange={(e) => setActor(e.target.value)}
          className="h-9 rounded-md border border-border bg-bg px-2 text-sm"
          aria-label="Actor filter"
        >
          <option value="">All actors</option>
          {facets.data?.actors.map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <select
          value={action}
          onChange={(e) => setAction(e.target.value)}
          className="h-9 rounded-md border border-border bg-bg px-2 text-sm"
          aria-label="Action filter"
        >
          <option value="">All actions</option>
          {facets.data?.actions.map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <select
          value={resource}
          onChange={(e) => setResource(e.target.value)}
          className="h-9 rounded-md border border-border bg-bg px-2 text-sm"
          aria-label="Resource filter"
        >
          <option value="">All resources</option>
          {facets.data?.resources.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
        <div className="flex items-center gap-1 rounded-md border border-border bg-bg px-2 text-sm">
          <span className="text-muted-fg">from</span>
          <input
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
            className="h-9 bg-transparent text-sm outline-none"
            aria-label="From date"
          />
          <span className="text-muted-fg">to</span>
          <input
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
            className="h-9 bg-transparent text-sm outline-none"
            aria-label="To date"
          />
        </div>
        {hasFilter && (
          <button
            type="button"
            onClick={() => {
              setActor("");
              setAction("");
              setResource("");
              setFromDate("");
              setToDate("");
            }}
            className="inline-flex h-9 items-center gap-1 rounded-md border border-border bg-bg px-3 text-sm text-muted-fg hover:text-fg"
          >
            <X className="h-4 w-4" /> Clear
          </button>
        )}
      </div>

      <table className="mt-6 w-full text-sm">
        <thead className="text-xs uppercase text-muted-fg">
          <tr>
            <th className="w-6"></th>
            <th className="text-left font-normal">When</th>
            <th className="text-left font-normal">Actor</th>
            <th className="text-left font-normal">Action</th>
            <th className="text-left font-normal">Resource</th>
            <th className="text-left font-normal">ID</th>
          </tr>
        </thead>
        <tbody>
          {(entries.data ?? []).map((e) => {
            const isOpen = expanded.has(e.id);
            const hasDetails = e.details && Object.keys(e.details).length > 0;
            return (
              <Fragment key={e.id}>
                <tr
                  className={cn(
                    "border-t border-border",
                    hasDetails && "cursor-pointer hover:bg-muted/30",
                  )}
                  // Keyboard-accessible expansion: Enter / Space toggles
                  // the detail row. The row becomes a button for keyboard
                  // users (role + tabIndex) without disturbing the
                  // native table semantics for screen readers, and
                  // aria-expanded keeps AT in sync with the disclosure.
                  role={hasDetails ? "button" : undefined}
                  tabIndex={hasDetails ? 0 : undefined}
                  aria-expanded={hasDetails ? isOpen : undefined}
                  onClick={() => hasDetails && toggle(e.id)}
                  onKeyDown={(evt) => {
                    if (!hasDetails) return;
                    if (evt.key === "Enter" || evt.key === " ") {
                      evt.preventDefault();
                      toggle(e.id);
                    }
                  }}
                >
                  <td className="py-2 pl-1">
                    {hasDetails ? (
                      isOpen ? (
                        <ChevronDown
                          className="h-4 w-4 text-muted-fg"
                          aria-label="Collapse details"
                        />
                      ) : (
                        <ChevronRight
                          className="h-4 w-4 text-muted-fg"
                          aria-label="Expand details"
                        />
                      )
                    ) : null}
                  </td>
                  <td className="py-2 text-xs tabular-nums">
                    {formatLocal(e.ts)}
                  </td>
                  <td className="py-2">{e.actor_email}</td>
                  <td
                    className={cn("py-2 font-medium", ACTION_TONE[e.action] ?? "")}
                  >
                    {e.action}
                  </td>
                  <td className="py-2 font-mono text-xs">{e.resource}</td>
                  <td className="py-2 font-mono text-xs text-muted-fg">
                    {e.resource_id ?? ""}
                  </td>
                </tr>
                {isOpen && hasDetails && (
                  <tr className="border-b border-border/60">
                    <td></td>
                    <td colSpan={5} className="px-2 py-2">
                      <pre className="overflow-x-auto rounded bg-muted/40 p-3 font-mono text-xs">
                        {JSON.stringify(e.details, null, 2)}
                      </pre>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
          {!entries.isPending && (entries.data ?? []).length === 0 && (
            <tr>
              <td colSpan={6} className="py-8 text-center text-sm text-muted-fg">
                {hasFilter ? "No audit entries match the current filters." : "No audit entries yet."}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
