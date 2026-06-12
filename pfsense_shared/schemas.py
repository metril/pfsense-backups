"""Pydantic schemas shared by the worker (IPC) and the web service (IPC + API).

IPC command/event shapes are the contract between the two services; both must
validate against the same models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# M1: chars we refuse in `name` and `backup_prefix`. These end up in glob
# patterns and filesystem paths inside the worker; the unsafe set keeps
# paths traversal-free and cleanup from walking outside the intended set.
_FS_UNSAFE = set("/\\*?[]<>|\"\x00")

# Canonical pfSense diag_backup.php subsystem identifiers. `""` means
# "Everything" (the pfSense default) and stays first so it's the
# zero-value for the dropdown. Tracks pfSense 2.7.x; extending this is a
# one-line tuple edit as new pfSense versions add areas.
PFSENSE_BACKUP_AREAS: tuple[str, ...] = (
    "",
    "aliases",
    "captiveportal",
    "certs",
    "cron",
    "dhcpd",
    "dhcpdv6",
    "dnsmasq",
    "filter",
    "firewallshaper",
    "ifgroups",
    "installedpackages",
    "interfaces",
    "ipsec",
    "load_balancer",
    "nat",
    "openvpn",
    "ppps",
    "rrddata",
    "schedules",
    "snmpd",
    "staticroutes",
    "syslog",
    "sysctl",
    "system",
    "system_advanced_admin",
    "system_advanced_firewall",
    "system_advanced_misc",
    "system_advanced_network",
    "system_advanced_notifications",
    "system_advanced_sysctl",
    "system_hasync",
    "unbound",
    "virtualip",
    "voucher",
    "vpn",
    "wol",
)
_PFSENSE_BACKUP_AREAS_SET = frozenset(PFSENSE_BACKUP_AREAS)


def _validate_backup_area(v: str | None) -> str | None:
    if v is None:
        return None
    if v not in _PFSENSE_BACKUP_AREAS_SET:
        raise ValueError(
            f"unknown pfSense backup area {v!r}; "
            f"expected one of: {sorted(PFSENSE_BACKUP_AREAS)!r}"
        )
    return v


def _no_fs_special(v: str) -> str:
    bad = sorted(ch for ch in set(v) if ch in _FS_UNSAFE)
    if bad:
        raise ValueError(
            f"contains filesystem-unsafe characters: {', '.join(repr(c) for c in bad)}"
        )
    if v.strip() != v:
        raise ValueError("must not have leading or trailing whitespace")
    if not v:
        raise ValueError("must not be empty")
    return v

# --------------------------------------------------------------------- #
# IPC commands (web → worker, ZMQ PUSH/PULL)
# --------------------------------------------------------------------- #


class BackupOverrides(BaseModel):
    """One-shot overrides for a manually triggered backup.

    Any field left None inherits the stored Instance value. The encrypt
    password crosses the ZMQ wire as Fernet ciphertext (bytes); the web
    router encrypts it before shipping, the worker decrypts on arrival.
    Plaintext never touches a persisted row.
    """

    model_config = ConfigDict(extra="forbid")

    backup_area: str | None = None
    backup_include_rrd: bool | None = None
    backup_include_packages: bool | None = None
    backup_include_ssh: bool | None = None
    backup_encrypt: bool | None = None
    # Fernet-encrypted override password. Only meaningful when
    # backup_encrypt is True; ignored otherwise.
    backup_encrypt_password_ct: bytes | None = None

    @field_validator("backup_area")
    @classmethod
    def _area_whitelist(cls, v: str | None) -> str | None:
        return _validate_backup_area(v)


class RunBackupCommand(BaseModel):
    cmd: Literal["run_backup"] = "run_backup"
    instance_id: int
    job_id: int
    # Optional one-shot overrides. Never persisted to the Instance row.
    overrides: BackupOverrides | None = None


class RunBackupAllCommand(BaseModel):
    cmd: Literal["run_backup_all"] = "run_backup_all"
    job_id: int
    # Optional one-shot overrides applied to every instance in the sweep.
    overrides: BackupOverrides | None = None


class TestConnectionCommand(BaseModel):
    cmd: Literal["test_connection"] = "test_connection"
    instance_id: int
    job_id: int


class ReloadScheduleCommand(BaseModel):
    cmd: Literal["reload_schedule"] = "reload_schedule"
    instance_id: int | None = None  # None → reload all


class SendTestNotificationCommand(BaseModel):
    cmd: Literal["send_test_notification"] = "send_test_notification"
    notification_id: int
    job_id: int


class ReencryptBackupsCommand(BaseModel):
    """Re-encrypt every encrypted Backup row for a single instance.

    The worker reads the *new* password by Fernet-decrypting the already-
    committed ``Instance.backup_encrypt_password_ct`` — nothing plaintext
    crosses the wire.
    """

    cmd: Literal["reencrypt_backups"] = "reencrypt_backups"
    instance_id: int
    job_id: int


class ReencryptAllBackupsCommand(BaseModel):
    """Re-encrypt every encrypted Backup row across every instance.

    ``new_password_ct`` is Fernet-encrypted by the web router and
    decrypted on the worker so plaintext never hits the ZMQ wire.
    ``also_update_instance_passwords`` flips every encrypted Instance to
    the same password so subsequent backups keep using it.
    """

    cmd: Literal["reencrypt_all_backups"] = "reencrypt_all_backups"
    job_id: int
    new_password_ct: bytes
    also_update_instance_passwords: bool = True


class TestReplicationCommand(BaseModel):
    """Round-trip a tiny object against the configured replication
    target. Runs on the worker (via IPC) so credentials and network
    reachability are tested from the process that will actually
    upload. Result comes back as a ``ReplicationTestResult`` event."""

    cmd: Literal["test_replication"] = "test_replication"
    request_id: str


class DeleteReplicaObjectCommand(BaseModel):
    """Best-effort remote-object delete, fired by the web when an
    operator manually deletes a backup that has an off-site copy. The
    row is already gone by the time this runs; failures just log (the
    orphan is caught by ``verify-replicas`` / lifecycle rules)."""

    cmd: Literal["delete_replica_object"] = "delete_replica_object"
    replica_key: str


class RetrieveReplicaCommand(BaseModel):
    """Download an off-site-only backup back to local storage: fetch
    the remote object, verify ``replica_sha256``, strip the replication
    encryption layer(s) added at upload, restore the original local
    file shape, and flip ``local_present`` back on."""

    cmd: Literal["retrieve_replica"] = "retrieve_replica"
    backup_id: int
    job_id: int


IpcCommand = (
    RunBackupCommand
    | RunBackupAllCommand
    | TestConnectionCommand
    | ReloadScheduleCommand
    | SendTestNotificationCommand
    | ReencryptBackupsCommand
    | ReencryptAllBackupsCommand
    | TestReplicationCommand
    | RetrieveReplicaCommand
    | DeleteReplicaObjectCommand
)


# --------------------------------------------------------------------- #
# IPC events (worker → web, ZMQ PUB/SUB)
# --------------------------------------------------------------------- #


class _BaseEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ts: datetime


class BackupStarted(_BaseEvent):
    topic: Literal["backup.started"] = "backup.started"
    job_id: int
    instance_id: int
    instance_name: str


class BackupProgress(_BaseEvent):
    topic: Literal["backup.progress"] = "backup.progress"
    job_id: int
    instance_id: int
    # NB: extending this literal is an IPC contract change — worker and
    # web must deploy together ("replicate" added in F3).
    phase: Literal["auth", "download", "save", "cleanup", "replicate"]


class BackupFinished(_BaseEvent):
    topic: Literal["backup.finished"] = "backup.finished"
    job_id: int
    instance_id: int
    success: bool
    duration_seconds: float
    filename: str
    size_bytes: int


class BackupFailed(_BaseEvent):
    topic: Literal["backup.failed"] = "backup.failed"
    job_id: int
    instance_id: int
    error: str


class ScheduleReloaded(_BaseEvent):
    topic: Literal["schedule.reloaded"] = "schedule.reloaded"
    instance_id: int | None


class TestConnectionResult(_BaseEvent):
    topic: Literal["test_connection.result"] = "test_connection.result"
    job_id: int
    instance_id: int
    ok: bool
    detail: str | None = None


class ReplicationTestResult(_BaseEvent):
    topic: Literal["replication_test.result"] = "replication_test.result"
    request_id: str
    ok: bool
    detail: str | None = None


class NotificationSent(_BaseEvent):
    topic: Literal["notification.sent"] = "notification.sent"
    notification_id: int
    success: bool
    detail: str | None = None


class WorkerHeartbeat(_BaseEvent):
    topic: Literal["worker.heartbeat"] = "worker.heartbeat"


class ReencryptStarted(_BaseEvent):
    topic: Literal["reencrypt.started"] = "reencrypt.started"
    job_id: int
    # None for the cross-instance ("all") variant.
    instance_id: int | None = None
    instance_name: str | None = None
    total: int


class ReencryptProgress(_BaseEvent):
    topic: Literal["reencrypt.progress"] = "reencrypt.progress"
    job_id: int
    instance_id: int | None = None
    processed: int
    total: int
    current_backup_id: int | None = None
    current_filename: str | None = None


class ReencryptFinished(_BaseEvent):
    topic: Literal["reencrypt.finished"] = "reencrypt.finished"
    job_id: int
    instance_id: int | None = None
    success_count: int
    failure_count: int
    # [{backup_id, filename, error}] per failed row.
    failures: list[dict[str, object]] = Field(default_factory=list)


IpcEvent = (
    BackupStarted
    | BackupProgress
    | BackupFinished
    | BackupFailed
    | ScheduleReloaded
    | TestConnectionResult
    | ReplicationTestResult
    | NotificationSent
    | WorkerHeartbeat
    | ReencryptStarted
    | ReencryptProgress
    | ReencryptFinished
)


# --------------------------------------------------------------------- #
# API schemas (web service REST I/O)
# --------------------------------------------------------------------- #


class InstanceCreate(BaseModel):
    name: str
    url: str
    username: str
    password: str
    subfolder: str | None = None
    backup_prefix: str = "daily"
    verify_ssl: bool = False
    timeout_seconds: int = Field(default=30, ge=1, le=3600)
    cron_expression: str | None = None
    # null = inherit BackupSettings.default_timezone.
    cron_timezone: str | None = None
    enabled: bool = True
    retention_count: int = Field(default=365, ge=0, le=10000)
    compress: bool = False
    # Off-site replication opt-in (F3).
    replicate: bool = False
    # Staleness alerting (F6): NULL = auto-derive from cron cadence.
    stale_after_hours: int | None = Field(default=None, ge=1, le=8760)
    # GFS retention tiers (F2): all NULL = count-only behavior.
    retention_keep_all_days: int | None = Field(default=None, ge=0, le=3650)
    retention_daily_days: int | None = Field(default=None, ge=0, le=3650)
    retention_weekly_weeks: int | None = Field(default=None, ge=0, le=520)
    retention_monthly_months: int | None = Field(default=None, ge=0, le=120)

    # Backup contents — defaults match today's hard-coded behavior so
    # upgrades don't change what gets captured.
    backup_area: str = ""
    backup_include_rrd: bool = False
    backup_include_packages: bool = True
    backup_include_ssh: bool = True
    backup_encrypt: bool = False
    # Plaintext on the wire; the router encrypts via Crypto before storing.
    # None when encryption is off.
    backup_encrypt_password: str | None = None

    @field_validator("name", "backup_prefix")
    @classmethod
    def _no_unsafe_chars(cls, v: str) -> str:
        return _no_fs_special(v)

    @field_validator("subfolder")
    @classmethod
    def _subfolder_safe(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return v
        # Single-segment only; no path traversal.
        # _no_fs_special blocks "/" and "\", but the standalone dotted
        # names "." and ".." also traverse when joined with a root
        # path — "Path(root) / '..'" resolves to the parent — so they
        # must be rejected explicitly.
        if v in {".", ".."}:
            raise ValueError("must not be '.' or '..'")
        return _no_fs_special(v)

    @field_validator("backup_area")
    @classmethod
    def _area_whitelist(cls, v: str) -> str:
        return _validate_backup_area(v) or ""


class InstanceUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    username: str | None = None
    password: str | None = Field(default=None, description="Blank → keep existing password")
    subfolder: str | None = None
    backup_prefix: str | None = None
    verify_ssl: bool | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    cron_expression: str | None = None
    cron_timezone: str | None = None
    enabled: bool | None = None
    retention_count: int | None = Field(default=None, ge=0, le=10000)
    compress: bool | None = None
    replicate: bool | None = None
    stale_after_hours: int | None = Field(default=None, ge=1, le=8760)
    retention_keep_all_days: int | None = Field(default=None, ge=0, le=3650)
    retention_daily_days: int | None = Field(default=None, ge=0, le=3650)
    retention_weekly_weeks: int | None = Field(default=None, ge=0, le=520)
    retention_monthly_months: int | None = Field(default=None, ge=0, le=120)

    backup_area: str | None = None
    backup_include_rrd: bool | None = None
    backup_include_packages: bool | None = None
    backup_include_ssh: bool | None = None
    backup_encrypt: bool | None = None
    # "__set__" sentinel = keep existing ciphertext. None = clear.
    # Any other string = new plaintext password to Fernet-encrypt.
    backup_encrypt_password: str | None = None
    # Pure request-side flag; no model column. When True, the router
    # fires a ReencryptBackupsCommand after the Instance update commits.
    reencrypt_existing_backups: bool = False

    @field_validator("name", "backup_prefix")
    @classmethod
    def _no_unsafe_chars(cls, v: str | None) -> str | None:
        return None if v is None else _no_fs_special(v)

    @field_validator("subfolder")
    @classmethod
    def _subfolder_safe(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return v
        if v in {".", ".."}:
            raise ValueError("must not be '.' or '..'")
        return _no_fs_special(v)

    @field_validator("backup_area")
    @classmethod
    def _area_whitelist(cls, v: str | None) -> str | None:
        return _validate_backup_area(v)


class InstanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    username: str
    subfolder: str | None
    backup_prefix: str
    verify_ssl: bool
    timeout_seconds: int
    cron_expression: str | None
    cron_timezone: str | None
    enabled: bool
    retention_count: int
    compress: bool
    replicate: bool
    stale_after_hours: int | None
    retention_keep_all_days: int | None
    retention_daily_days: int | None
    retention_weekly_weeks: int | None
    retention_monthly_months: int | None

    backup_area: str
    backup_include_rrd: bool
    backup_include_packages: bool
    backup_include_ssh: bool
    backup_encrypt: bool
    # "__set__" when a ciphertext is stored, else None. Never plaintext.
    backup_encrypt_password: str | None = None

    created_at: datetime
    updated_at: datetime


class ReplicationSettingsRead(BaseModel):
    """Secrets read back as the ``__set__`` sentinel, never plaintext."""

    enabled: bool
    kind: Literal["s3", "sftp"]
    s3_endpoint_url: str | None
    s3_region: str | None
    s3_bucket: str | None
    s3_access_key_id: str | None
    s3_secret_access_key: str | None  # "__set__" | None
    sftp_host: str | None
    sftp_port: int
    sftp_username: str | None
    sftp_password: str | None  # "__set__" | None
    sftp_private_key: str | None  # "__set__" | None
    base_path: str
    encrypt_plaintext: bool
    double_encrypt: bool
    replication_password: str | None  # "__set__" | None
    mirror_deletes: bool


class ReplicationSettingsUpdate(BaseModel):
    """Secrets follow the instance-password convention: ``"__set__"``
    sentinel = keep existing ciphertext, None/empty = clear, any other
    string = new plaintext to Fernet-encrypt."""

    enabled: bool | None = None
    kind: Literal["s3", "sftp"] | None = None
    s3_endpoint_url: str | None = None
    s3_region: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    sftp_host: str | None = None
    sftp_port: int | None = Field(default=None, ge=1, le=65535)
    sftp_username: str | None = None
    sftp_password: str | None = None
    sftp_private_key: str | None = None
    base_path: str | None = None
    encrypt_plaintext: bool | None = None
    double_encrypt: bool | None = None
    replication_password: str | None = None
    mirror_deletes: bool | None = None


ApiTokenScope = Literal["read", "write"]


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scope: ApiTokenScope = "read"
    # Days until expiry; None = never expires.
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class ApiTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    prefix: str
    scope: ApiTokenScope
    enabled: bool
    created_by: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None


class ApiTokenCreated(ApiTokenRead):
    """Create response — the only place the plaintext secret appears."""

    token: str


class ApiTokenUpdate(BaseModel):
    enabled: bool | None = None


class BackupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    instance_id: int
    instance_name: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    filename: str
    size_bytes: int
    compressed: bool
    success: bool
    error_message: str | None
    tag: str | None = None
    note: str | None = None

    # Contents snapshot — what pfSense actually handed back on this row.
    area: str = ""
    included_rrd: bool = False
    included_packages: bool = True
    included_ssh: bool = True
    encrypted: bool = False


class BackupUpdate(BaseModel):
    """Partial patch for user-editable Backup metadata (tag + note only)."""

    tag: str | None = None
    note: str | None = None


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    instance_id: int | None
    kind: str
    requested_by: str | None
    requested_at: datetime
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    message: str | None


NotificationKind = Literal["discord", "home_assistant", "ntfy", "healthchecks", "webhook"]

# ``change`` fires only when a successful backup's vs-previous diff is
# non-empty (with a "Changes: +A / -R / ~M" summary in the message).
# ``stale`` fires from the worker's staleness sweep (no successful
# backup within the instance's threshold) + the matching recovery.
NotificationTrigger = Literal["success", "failure", "always", "change", "stale"]


class NotificationCreate(BaseModel):
    name: str
    kind: NotificationKind = "webhook"
    url: str = ""
    trigger: NotificationTrigger = "always"
    enabled: bool = True
    message_format: str = "{status}: pfSense backup completed. {details}"
    include_instance_details: bool = True
    timeout_seconds: int = 10
    headers: dict[str, str] | None = None
    payload_template: dict[str, object] | None = None
    config: dict[str, object] | None = None
    instance_ids: list[int] | None = None


class NotificationUpdate(BaseModel):
    name: str | None = None
    kind: NotificationKind | None = None
    url: str | None = None
    trigger: NotificationTrigger | None = None
    enabled: bool | None = None
    message_format: str | None = None
    include_instance_details: bool | None = None
    timeout_seconds: int | None = None
    headers: dict[str, str] | None = None
    payload_template: dict[str, object] | None = None
    config: dict[str, object] | None = None
    instance_ids: list[int] | None = None


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: NotificationKind
    url: str
    trigger: str
    enabled: bool
    message_format: str
    include_instance_details: bool
    timeout_seconds: int
    headers: dict[str, str] | None = None
    payload_template: dict[str, object] | None = None
    config: dict[str, object] | None = None
    instance_ids: list[int] | None = None


class BackupSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    filename_format: str
    timestamp_format: str
    directory: str
    default_timezone: str
    backup_all_max_workers: int


class BackupSettingsUpdate(BaseModel):
    filename_format: str | None = None
    timestamp_format: str | None = None
    directory: str | None = None
    default_timezone: str | None = None
    backup_all_max_workers: int | None = None


class LoggingSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    level: str
    format: str


class LoggingSettingsUpdate(BaseModel):
    level: str | None = None
    format: str | None = None


class ScheduleUpdate(BaseModel):
    cron_expression: str | None = None
    # null = inherit BackupSettings.default_timezone.
    cron_timezone: str | None = None
    enabled: bool = True
