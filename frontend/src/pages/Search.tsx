/** Global config search (F4): substring search over every instance's
 * anchor-event history — "when did 192.0.2.5 appear anywhere?".
 *
 * Each hit deep-links two ways, reusing the existing xref machinery:
 * "open in backup" → BackupView with ``?anchor=`` (scroll + flash),
 * and the history icon → AnchorHistoryDrawer for (instance, anchor).
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { History, Search as SearchIcon } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import { QueryError } from "@/components/ui/QueryError";
import { Select } from "@/components/ui/Select";
import { AnchorHistoryDrawer } from "@/components/xref/AnchorHistoryDrawer";
import { useGlobalSearch, useInstances } from "@/api/queries";
import type { SearchHit } from "@/api/types";
import { useDebouncedValue } from "@/lib/useDebouncedValue";
import { formatLocal } from "@/lib/datetime";

const KIND_ALL = "__all__";
const INSTANCE_ALL = "__all__";

const KIND_TONE: Record<SearchHit["kind"], "success" | "warn" | "danger" | "muted"> = {
  added: "success",
  modified: "warn",
  removed: "danger",
  reordered: "muted",
};

export function SearchPage() {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState(KIND_ALL);
  const [instanceId, setInstanceId] = useState(INSTANCE_ALL);
  const [openDrawer, setOpenDrawer] = useState<{
    instanceId: number;
    anchor: string;
  } | null>(null);

  const debounced = useDebouncedValue(query, 300);
  const instances = useInstances();
  const search = useGlobalSearch(debounced, {
    instanceId: instanceId === INSTANCE_ALL ? undefined : Number(instanceId),
    kind: kind === KIND_ALL ? undefined : kind,
  });

  const hits = (search.data?.pages ?? []).flatMap((p) => p.hits);
  const active = debounced.trim().length >= 2;

  return (
    <div>
      <h1 className="text-2xl font-semibold">Search</h1>
      <p className="mt-1 text-sm text-muted-fg">
        Find a value or setting anywhere in any instance's change history.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[280px] flex-1">
          <SearchIcon className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-fg" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="IP, hostname, alias name, anchor id…"
            className="pl-8"
            aria-label="Search query"
          />
        </div>
        <Select
          value={instanceId}
          onChange={setInstanceId}
          options={[
            { value: INSTANCE_ALL, label: "All instances" },
            ...(instances.data ?? []).map((i) => ({
              value: String(i.id),
              label: i.name,
            })),
          ]}
          aria-label="Instance filter"
          className="w-44"
        />
        <Select
          value={kind}
          onChange={setKind}
          options={[
            { value: KIND_ALL, label: "All kinds" },
            { value: "added", label: "added" },
            { value: "modified", label: "modified" },
            { value: "removed", label: "removed" },
            { value: "reordered", label: "reordered" },
          ]}
          aria-label="Change kind filter"
          className="w-36"
        />
      </div>

      {search.isError && (
        <div className="mt-6">
          <QueryError title="Search failed" error={search.error} />
        </div>
      )}

      {active && hits.length > 0 && (
        <table className="mt-6 w-full text-sm">
          <thead className="text-xs uppercase text-muted-fg">
            <tr>
              <th className="px-3 text-left font-normal">When</th>
              <th className="px-3 text-left font-normal">Instance</th>
              <th className="px-3 text-left font-normal">Section</th>
              <th className="px-3 text-left font-normal">What</th>
              <th className="px-3 text-left font-normal">Kind</th>
              <th className="px-3 text-left font-normal">Match</th>
              <th className="w-10 px-3"></th>
            </tr>
          </thead>
          <tbody>
            {hits.map((h) => (
              <tr key={h.event_id} className="border-t border-border align-middle">
                <td className="px-3 py-2 text-xs whitespace-nowrap">
                  {formatLocal(h.occurred_at)}
                </td>
                <td className="px-3 py-2">{h.instance_name}</td>
                <td className="px-3 py-2 text-xs text-muted-fg">
                  {h.section ?? "—"}
                </td>
                <td className="px-3 py-2">
                  <Link
                    to={`/backups/${h.backup_id}/view?anchor=${encodeURIComponent(h.anchor_id)}`}
                    className="hover:text-accent"
                    title="Open in backup view"
                  >
                    {h.label}
                  </Link>
                </td>
                <td className="px-3 py-2">
                  <Badge tone={KIND_TONE[h.kind]}>{h.kind}</Badge>
                </td>
                <td className="max-w-md px-3 py-2">
                  <code className="block truncate font-mono text-xs text-muted-fg">
                    {h.excerpt}
                  </code>
                </td>
                <td className="px-3 py-2 text-right">
                  <Button
                    variant="ghost"
                    size="icon"
                    title="Blame history"
                    aria-label={`History for ${h.label}`}
                    onClick={() =>
                      setOpenDrawer({
                        instanceId: h.instance_id,
                        anchor: h.anchor_id,
                      })
                    }
                  >
                    <History className="h-4 w-4" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {active && search.hasNextPage && (
        <div className="mt-4 flex justify-center">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => search.fetchNextPage()}
            disabled={search.isFetchingNextPage}
          >
            {search.isFetchingNextPage ? "Loading…" : "Load more"}
          </Button>
        </div>
      )}

      {active && !search.isPending && !search.isError && hits.length === 0 && (
        <div className="mt-8">
          <EmptyState
            icon={<SearchIcon className="h-8 w-8" />}
            headline="No matches"
            body="Nothing in any instance's change history matches that query. Note: history only covers retained backups."
          />
        </div>
      )}

      {!active && (
        <div className="mt-8 text-sm text-muted-fg">
          Type at least two characters to search.
        </div>
      )}

      {openDrawer && (
        <AnchorHistoryDrawer
          instanceId={openDrawer.instanceId}
          anchor={openDrawer.anchor}
          onClose={() => setOpenDrawer(null)}
        />
      )}
    </div>
  );
}
