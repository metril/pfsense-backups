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
  Instance,
  InstanceCreate,
  InstanceUpdate,
  Job,
  Notification,
  PreflightRequest,
  PreflightResponse,
  ScheduleRow,
  SettingsBackup,
  SettingsLogging,
} from "./types";

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

export function useUpdateInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: InstanceUpdate }) =>
      api.put<Instance>(`/api/instances/${id}`, patch),
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
    mutationFn: (id: number) => api.post<{ job_id: number }>(`/api/instances/${id}/backup-now`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

export function useBackupAll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ job_id: number }>("/api/backups/run-all"),
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
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backups"] }),
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
