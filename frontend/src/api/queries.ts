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
  AuthUser,
  BackupListItem,
  Instance,
  InstanceCreate,
  InstanceUpdate,
  Job,
  Notification,
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

export function useBackupNow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.post<{ job_id: number }>(`/api/instances/${id}/backup-now`),
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

export function useSchedules() {
  return useQuery({ queryKey: ["schedule"], queryFn: () => api.get<ScheduleRow[]>("/api/schedule") });
}

export function useUpdateSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      cron_expression,
      cron_timezone,
      enabled,
    }: {
      id: number;
      cron_expression: string | null;
      cron_timezone: string;
      enabled: boolean;
    }) =>
      api.put<ScheduleRow>(`/api/schedule/${id}`, {
        cron_expression,
        cron_timezone,
        enabled,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["schedule"] });
      qc.invalidateQueries({ queryKey: ["instances"] });
    },
  });
}

export async function previewCron(cron: string, tz: string = "UTC") {
  return api.get<{ cron: string; description: string; next_runs: string[] }>(
    `/api/schedule/_tools/preview?cron=${encodeURIComponent(cron)}&tz=${encodeURIComponent(tz)}`,
  );
}

// ----------------- backups -----------------

export function useBackups(instanceId?: number) {
  return useQuery({
    queryKey: ["backups", instanceId ?? "all"],
    queryFn: () =>
      api.get<BackupListItem[]>(
        instanceId === undefined ? "/api/backups" : `/api/backups?instance_id=${instanceId}`,
      ),
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

// ----------------- helpers -----------------

function invalidateInstanceViews(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ["instances"] });
  qc.invalidateQueries({ queryKey: ["schedule"] });
}
