// Types matching pfsense_shared/schemas.py REST I/O models.

export interface AuthUser {
  email: string;
  name: string | null;
  picture: string | null;
}

export interface Instance {
  id: number;
  name: string;
  url: string;
  username: string;
  subfolder: string | null;
  backup_prefix: string;
  verify_ssl: boolean;
  timeout_seconds: number;
  cron_expression: string | null;
  /** null = inherit BackupSettings.default_timezone. */
  cron_timezone: string | null;
  enabled: boolean;
  retention_count: number;
  compress: boolean;
  /** Backup contents — what pfSense diag_backup.php will return. */
  backup_area: string;
  backup_include_rrd: boolean;
  backup_include_packages: boolean;
  backup_include_ssh: boolean;
  backup_encrypt: boolean;
  /** "__set__" when a ciphertext is stored, else null. Never plaintext. */
  backup_encrypt_password: string | null;
  created_at: string;
  updated_at: string;
}

export interface InstanceCreate {
  name: string;
  url: string;
  username: string;
  password: string;
  subfolder?: string | null;
  backup_prefix?: string;
  verify_ssl?: boolean;
  timeout_seconds?: number;
  cron_expression?: string | null;
  /** null = inherit BackupSettings.default_timezone. */
  cron_timezone?: string | null;
  enabled?: boolean;
  retention_count?: number;
  compress?: boolean;

  backup_area?: string;
  backup_include_rrd?: boolean;
  backup_include_packages?: boolean;
  backup_include_ssh?: boolean;
  backup_encrypt?: boolean;
  /** Plaintext on writes; never echoed back. */
  backup_encrypt_password?: string | null;
}

export type InstanceUpdate = Partial<InstanceCreate> & {
  /**
   * Send "__set__" to keep the existing ciphertext, null to clear,
   * any other string to set a new password.
   */
  backup_encrypt_password?: string | null;
  /** Pair with a password change to re-encrypt every backup this instance has. */
  reencrypt_existing_backups?: boolean;
};

/** One-shot overrides for a "Backup now" / "Backup all" call. */
export interface BackupOverridesRequest {
  backup_area?: string;
  backup_include_rrd?: boolean;
  backup_include_packages?: boolean;
  backup_include_ssh?: boolean;
  backup_encrypt?: boolean;
  backup_encrypt_password?: string | null;
}

export interface ReencryptAllRequest {
  new_password: string;
  confirm_password: string;
  also_update_instance_passwords: boolean;
}

export interface DiffCounts {
  added: number;
  removed: number;
  modified: number;
}

export interface BackupListItem {
  id: number;
  instance_id: number;
  instance_name: string;
  started_at: string;
  finished_at: string;
  duration_seconds: number;
  filename: string;
  size_bytes: number;
  compressed: boolean;
  success: boolean;
  tag: string | null;
  note: string | null;
  /** Contents snapshot — what pfSense actually handed back on this row. */
  area: string;
  included_rrd: boolean;
  included_packages: boolean;
  included_ssh: boolean;
  encrypted: boolean;
  /** v0.37.0 — precomputed "+N since first backup" summary. Null for
   *  backups taken before v0.37.0 (or when compute skipped / failed);
   *  the UI renders null as a quiet "—". */
  changes_since_first: DiffCounts | null;
}

export interface DiffSummaryResponse {
  backup_id: number;
  vs_previous: DiffCounts | null;
  vs_first: DiffCounts | null;
  first_backup_id: number | null;
  first_backup_started_at: string | null;
}

export interface ScheduleRow {
  instance_id: number;
  instance_name: string;
  cron_expression: string | null;
  /** Override (null when instance is inheriting the global default). */
  cron_timezone: string | null;
  /** What the scheduler actually uses — cron_timezone ?? default_timezone. */
  effective_timezone: string;
  enabled: boolean;
  description: string;
  next_runs: string[];
}

export type NotificationKind =
  | "discord"
  | "home_assistant"
  | "ntfy"
  | "healthchecks"
  | "webhook";

export interface Notification {
  id: number;
  name: string;
  kind: NotificationKind;
  url: string;
  trigger: "success" | "failure" | "always";
  enabled: boolean;
  message_format: string;
  include_instance_details: boolean;
  timeout_seconds: number;
  headers: Record<string, string> | null;
  payload_template: Record<string, unknown> | null;
  /** Kind-specific structured config. Secrets are returned as "__set__". */
  config: Record<string, unknown> | null;
  /** null or [] = all instances (default). */
  instance_ids: number[] | null;
}

export interface AuditEntry {
  id: number;
  ts: string;
  actor_email: string;
  action: string;
  resource: string;
  resource_id: string | null;
  details: Record<string, unknown> | null;
}

export interface AuditFacets {
  actors: string[];
  actions: string[];
  resources: string[];
}

export interface PreflightRequest {
  instance_id?: number;
  url?: string;
  username?: string;
  password?: string;
  verify_ssl?: boolean;
  timeout_seconds?: number;
}

export interface PreflightResponse {
  ok: boolean;
  detail: string;
  duration_ms: number;
}

export interface Job {
  id: number;
  instance_id: number | null;
  kind: string;
  requested_by: string | null;
  requested_at: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  message: string | null;
}

export interface SettingsBackup {
  filename_format: string;
  timestamp_format: string;
  directory: string;
  default_timezone: string;
  backup_all_max_workers: number;
}

export interface SettingsLogging {
  level: string;
  format: string;
}

export interface AllSettings {
  backup: SettingsBackup | null;
  logging: SettingsLogging | null;
}

// -------- Event envelope from /api/events WebSocket --------
export type EventEnvelope =
  | { topic: "backup.started"; job_id: number; instance_id: number; instance_name: string; ts: string }
  | { topic: "backup.progress"; job_id: number; instance_id: number; phase: string; ts: string }
  | { topic: "backup.finished"; job_id: number; instance_id: number; success: boolean; duration_seconds: number; filename: string; size_bytes: number; ts: string }
  | { topic: "backup.failed"; job_id: number; instance_id: number; error: string; ts: string }
  | { topic: "schedule.reloaded"; instance_id: number | null; ts: string }
  | { topic: "test_connection.result"; job_id: number; instance_id: number; ok: boolean; detail: string | null; ts: string }
  | { topic: "notification.sent"; notification_id: number; success: boolean; detail: string | null; ts: string }
  | { topic: "worker.heartbeat"; ts: string }
  | { topic: "reencrypt.started"; job_id: number; instance_id: number | null; instance_name: string | null; total: number; ts: string }
  | { topic: "reencrypt.progress"; job_id: number; instance_id: number | null; processed: number; total: number; current_backup_id: number | null; current_filename: string | null; ts: string }
  | { topic: "reencrypt.finished"; job_id: number; instance_id: number | null; success_count: number; failure_count: number; failures: Array<{ backup_id: number; filename: string; error: string }>; ts: string };
