// TanStack Query hooks bound to the REST surface.

import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { api } from "./client";
import type {
  AllSettings,
  AuditEntry,
  AuditFacets,
  AuthUser,
  BackupListItem,
  BackupOverridesRequest,
  Instance,
  InstanceCreate,
  InstanceUpdate,
  Job,
  Notification,
  PreflightRequest,
  PreflightResponse,
  ReencryptAllRequest,
  ScheduleRow,
  SettingsBackup,
  SettingsLogging,
} from "./types";
import type { ConfigDiff, ParsedConfig } from "./parsedTypes";

// ----------------- auth -----------------

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<AuthUser>("/api/auth/me"),
    retry: false,
  });
}

export function useAuthStatus() {
  return useQuery({
    queryKey: ["auth-status"],
    queryFn: () => api.get<{ authenticated: boolean; email: string | null }>("/api/auth/status"),
    retry: false,
    refetchOnWindowFocus: false,
  });
}

// ----------------- health -----------------

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => api.get<{ ok: boolean; worker_alive: boolean }>("/api/health"),
    refetchInterval: 10000,
  });
}

// ----------------- instances -----------------

export function useInstances() {
  return useQuery({ queryKey: ["instances"], queryFn: () => api.get<Instance[]>("/api/instances") });
}

export function useInstance(id: number | null) {
  return useQuery({
    queryKey: ["instances", id],
    queryFn: () => api.get<Instance>(`/api/instances/${id}`),
    enabled: id !== null,
  });
}

export function useCreateInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: InstanceCreate) => api.post<Instance>("/api/instances", payload),
    onSuccess: () => invalidateInstanceViews(qc),
  });
}

/**
 * Response from PUT /api/instances/{id}. When the operator ticks
 * "re-encrypt existing backups" and the password actually changes,
 * the server adds a `reencrypt_job_id` so the UI can open the progress
 * toast that listens on reencrypt.* events.
 */
export type InstanceUpdateResponse = Instance & { reencrypt_job_id?: number };

export function useUpdateInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: InstanceUpdate }) =>
      api.put<InstanceUpdateResponse>(`/api/instances/${id}`, patch),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["instances", vars.id] });
      invalidateInstanceViews(qc);
    },
  });
}

export function useDeleteInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.delete(`/api/instances/${id}`),
    onSuccess: () => invalidateInstanceViews(qc),
  });
}

export function useTestConnection() {
  return useMutation({
    mutationFn: (id: number) => api.post<{ job_id: number }>(`/api/instances/${id}/test-connection`),
  });
}

export function usePreflight() {
  return useMutation({
    mutationFn: (payload: PreflightRequest) =>
      api.post<PreflightResponse>("/api/instances/preflight", payload),
  });
}

export function useBackupNow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      overrides,
    }: {
      id: number;
      overrides?: BackupOverridesRequest;
    }) =>
      api.post<{ job_id: number }>(
        `/api/instances/${id}/backup-now`,
        overrides,
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

export function useBackupAll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (overrides?: BackupOverridesRequest) =>
      api.post<{ job_id: number }>("/api/backups/run-all", overrides),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

export function useReencryptAll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ReencryptAllRequest) =>
      api.post<{ job_id: number }>("/api/backups/reencrypt-all", payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

export function useImportBackups() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      api.post<{ imported: number; skipped: number; scanned_dir: string }>(
        `/api/instances/${id}/import-backups`,
      ),
    onSuccess: () => {
      // New backup rows invalidate the backup list AND any
      // instance-level views (last-seen time, backup count) that
      // derive their summary from the backups table.
      qc.invalidateQueries({ queryKey: ["backups"] });
      invalidateInstanceViews(qc);
    },
  });
}

// ----------------- schedule -----------------
// Read-only hook; schedule edits flow through the Instance editor now.
// The PUT /api/schedule/{id} + GET /api/schedule/_tools/preview endpoints
// remain on the server for API/rollback stability but no frontend caller
// exercises them.

export function useSchedules() {
  return useQuery({ queryKey: ["schedule"], queryFn: () => api.get<ScheduleRow[]>("/api/schedule") });
}

// ----------------- backups -----------------

export type BackupSort = "started_at" | "size_bytes" | "duration_seconds" | "filename";
export type BackupOrder = "asc" | "desc";

export interface BackupFilter {
  instanceId?: number;
  startedFrom?: string; // ISO-8601, inclusive
  startedTo?: string;   // ISO-8601, inclusive
  sort?: BackupSort;
  order?: BackupOrder;
}

export function useBackups(filter: BackupFilter | number | undefined = undefined) {
  // Back-compat: callers that still pass a bare instanceId get the same
  // behavior as before (all date-range params omitted).
  const f: BackupFilter =
    typeof filter === "number" ? { instanceId: filter } : (filter ?? {});

  const params = new URLSearchParams();
  if (f.instanceId !== undefined) params.set("instance_id", String(f.instanceId));
  if (f.startedFrom) params.set("started_from", f.startedFrom);
  if (f.startedTo) params.set("started_to", f.startedTo);
  if (f.sort) params.set("sort", f.sort);
  if (f.order) params.set("order", f.order);
  const qs = params.toString();

  return useQuery({
    queryKey: [
      "backups",
      f.instanceId ?? "all",
      f.startedFrom ?? "",
      f.startedTo ?? "",
      f.sort ?? "started_at",
      f.order ?? "desc",
    ],
    queryFn: () =>
      api.get<BackupListItem[]>(qs ? `/api/backups?${qs}` : "/api/backups"),
  });
}

export function useUpdateBackup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: { tag?: string | null; note?: string | null } }) =>
      api.patch<{ id: number; tag: string | null; note: string | null }>(
        `/api/backups/${id}`,
        patch,
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backups"] }),
  });
}

export function useDeleteBackup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.delete(`/api/backups/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backups"] }),
  });
}

/** Positions map returned alongside the parsed config. Keyed by
 *  the same anchor ids the viewer emits (``xref-…``, ``field-…``,
 *  ``section-…``); value is a 1-based ``[start_line, end_line]``
 *  tuple pointing at the corresponding element in the raw XML.
 *  Used by the Structured ↔ Raw XML tab-switch sync to reveal the
 *  same content in Monaco. */
export type XrefPositions = Record<string, [number, number]>;

export interface ParsedBackupResponse {
  config: ParsedConfig;
  positions: XrefPositions;
}

/** Structured projection of a backup's config.xml (server-side parsed,
 *  redacted). Never includes secrets — the server replaces password
 *  hashes, PSKs, cert private keys, and RADIUS/LDAP secrets with a
 *  ***redacted*** placeholder.
 *
 *  v0.22.0 wrapped the response so the positions map ships in the
 *  same payload — zero extra round trip for tab-switch sync. */
export function useParsedBackup(id: number) {
  return useQuery({
    queryKey: ["backups", id, "parsed"],
    queryFn: () => api.get<ParsedBackupResponse>(`/api/backups/${id}/parsed`),
    // Parser output is static for a given backup — never refetch on focus.
    staleTime: Infinity,
  });
}

// ----- v0.24.0: per-anchor blame / history ----------

export interface AnchorHistoryChange {
  backup_id: number;
  started_at: string;
  /** Row-shaped anchors return an object (Record<string, unknown>),
   *  singleton field anchors a stringified scalar, missing anchors
   *  ``null``. Drawer renders each shape differently. */
  value: Record<string, unknown> | string | null;
  is_change: boolean;
}

export interface AnchorHistoryResponse {
  anchor: string;
  instance_id: number;
  entries: AnchorHistoryChange[];
  /** v0.40.0: True when served from the indexed ``anchor_event`` table,
   *  false when the instance hasn't been backfilled yet and we fell
   *  back to the per-request snapshot walk. */
  indexed?: boolean;
}

// ----- v0.40.0: blame tooltip + cumulative changes ----------

export interface AnchorBlameSummaryEntry {
  backup_id: number;
  occurred_at: string;
  kind: "added" | "modified" | "removed" | "reordered";
}

export interface AnchorBlameSummaryResponse {
  as_of_backup_id: number;
  anchors: Record<string, AnchorBlameSummaryEntry>;
  indexed: boolean;
}

/** Prefetch the whole instance's "latest event per anchor" map.
 *  Frontend keeps it in TanStack cache for the page lifetime so the
 *  inline tooltip (``AnchorBlameTooltip``) never makes a per-hover
 *  request. Returns ``indexed=false`` for pre-v0.40.0 instances;
 *  callers use that to decide whether to surface the tooltip at all. */
export function useAnchorBlameSummary(
  instanceId: number | null | undefined,
  asOfBackupId?: number | null,
) {
  return useQuery({
    queryKey: ["instance-anchor-blame-summary", instanceId, asOfBackupId ?? null],
    queryFn: () => {
      const q = asOfBackupId != null ? `?as_of_backup_id=${asOfBackupId}` : "";
      return api.get<AnchorBlameSummaryResponse>(
        `/api/backups/instance/${instanceId}/anchor-blame-summary${q}`,
      );
    },
    enabled: Boolean(instanceId),
    staleTime: 10 * 60 * 1000,
  });
}

export interface CumulativeChangeRow {
  anchor_id: string;
  section: string | null;
  label: string;
  first_seen_at: string;
  last_change_at: string;
  change_count: number;
  latest_kind: "added" | "modified" | "removed" | "reordered";
  original_value: unknown;
  current_value: unknown;
}

export interface CumulativeChangesResponse {
  since_backup_id: number;
  until_backup_id: number;
  rows: CumulativeChangeRow[];
  indexed: boolean;
}

export function useCumulativeChanges(
  instanceId: number | null | undefined,
  sinceBackupId?: number | null,
  untilBackupId?: number | null,
) {
  return useQuery({
    queryKey: [
      "instance-cumulative-changes",
      instanceId,
      sinceBackupId ?? null,
      untilBackupId ?? null,
    ],
    queryFn: () => {
      const qs = new URLSearchParams();
      if (sinceBackupId != null) qs.set("since_backup_id", String(sinceBackupId));
      if (untilBackupId != null) qs.set("until_backup_id", String(untilBackupId));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return api.get<CumulativeChangesResponse>(
        `/api/backups/instance/${instanceId}/cumulative-changes${suffix}`,
      );
    },
    enabled: Boolean(instanceId),
    staleTime: 5 * 60 * 1000,
  });
}

/** Walk every successful backup of the given instance and resolve
 *  the named anchor on each, returning a change timeline. Enabled
 *  only when both ``instanceId`` and ``anchor`` are supplied so the
 *  query doesn't fire for a closed drawer. */
export function useAnchorHistory(
  instanceId: number | null | undefined,
  anchor: string | null,
) {
  return useQuery({
    queryKey: ["instance-anchor-history", instanceId, anchor],
    queryFn: () =>
      api.get<AnchorHistoryResponse>(
        `/api/backups/instance/${instanceId}/anchor-history?anchor=${encodeURIComponent(anchor ?? "")}`,
      ),
    enabled: Boolean(instanceId) && Boolean(anchor),
    staleTime: 5 * 60 * 1000, // blame rarely changes while drawer is open
  });
}

export function useParsedDiffPair(a: number | null, b: number | null) {
  return useQuery({
    queryKey: ["backups", "diff", a, b, "parsed"],
    queryFn: () =>
      api.get<ConfigDiff>(`/api/backups/diff/pair/parsed?a=${a}&b=${b}`),
    enabled: a !== null && b !== null,
    staleTime: Infinity,
  });
}

// ----------------- notifications -----------------

export function useNotifications() {
  return useQuery({ queryKey: ["notifications"], queryFn: () => api.get<Notification[]>("/api/notifications") });
}

export function useCreateNotification() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Omit<Notification, "id">) => api.post<Notification>("/api/notifications", payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
}

export function useUpdateNotification() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Partial<Omit<Notification, "id">> }) =>
      api.put<Notification>(`/api/notifications/${id}`, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
}

export function useDeleteNotification() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.delete(`/api/notifications/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
}

export function useSendTestNotification() {
  return useMutation({
    mutationFn: (id: number) => api.post<{ job_id: number }>(`/api/notifications/${id}/test`),
  });
}

// ----------------- settings -----------------

export function useSettings() {
  return useQuery({ queryKey: ["settings"], queryFn: () => api.get<AllSettings>("/api/settings") });
}

export function useUpdateBackupSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<SettingsBackup>) => api.put<SettingsBackup>("/api/settings/backup", patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });
}

export function useUpdateLoggingSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<SettingsLogging>) => api.put<SettingsLogging>("/api/settings/logging", patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });
}

// ----------------- jobs -----------------

export function useJobs(instanceId?: number) {
  return useQuery({
    queryKey: ["jobs", instanceId ?? "all"],
    queryFn: () =>
      api.get<Job[]>(instanceId === undefined ? "/api/jobs" : `/api/jobs?instance_id=${instanceId}`),
  });
}

// ----------------- audit -----------------

export interface AuditFilter {
  actor?: string;
  action?: string;
  resource?: string;
  tsFrom?: string;
  tsTo?: string;
  limit?: number;
  offset?: number;
}

export function useAuditLog(filter: AuditFilter = {}) {
  const params = new URLSearchParams();
  if (filter.actor) params.set("actor", filter.actor);
  if (filter.action) params.set("action", filter.action);
  if (filter.resource) params.set("resource", filter.resource);
  if (filter.tsFrom) params.set("ts_from", filter.tsFrom);
  if (filter.tsTo) params.set("ts_to", filter.tsTo);
  if (filter.limit !== undefined) params.set("limit", String(filter.limit));
  if (filter.offset !== undefined) params.set("offset", String(filter.offset));
  const qs = params.toString();
  return useQuery({
    queryKey: ["audit", qs],
    queryFn: () => api.get<AuditEntry[]>(qs ? `/api/audit?${qs}` : "/api/audit"),
  });
}

export function useAuditFacets() {
  return useQuery({
    queryKey: ["audit-facets"],
    queryFn: () => api.get<AuditFacets>("/api/audit/facets"),
    staleTime: 60_000,
  });
}

// ----------------- helpers -----------------

function invalidateInstanceViews(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ["instances"] });
  qc.invalidateQueries({ queryKey: ["schedule"] });
}
