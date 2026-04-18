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


class RunBackupCommand(BaseModel):
    cmd: Literal["run_backup"] = "run_backup"
    instance_id: int
    job_id: int


class RunBackupAllCommand(BaseModel):
    cmd: Literal["run_backup_all"] = "run_backup_all"
    job_id: int


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


IpcCommand = (
    RunBackupCommand
    | RunBackupAllCommand
    | TestConnectionCommand
    | ReloadScheduleCommand
    | SendTestNotificationCommand
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
    phase: Literal["auth", "download", "save", "cleanup"]


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


class NotificationSent(_BaseEvent):
    topic: Literal["notification.sent"] = "notification.sent"
    notification_id: int
    success: bool
    detail: str | None = None


class WorkerHeartbeat(_BaseEvent):
    topic: Literal["worker.heartbeat"] = "worker.heartbeat"


IpcEvent = (
    BackupStarted
    | BackupProgress
    | BackupFinished
    | BackupFailed
    | ScheduleReloaded
    | TestConnectionResult
    | NotificationSent
    | WorkerHeartbeat
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
    cron_timezone: str = "UTC"
    enabled: bool = True
    retention_count: int = Field(default=365, ge=0, le=10000)
    compress: bool = False

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
        return _no_fs_special(v)


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

    @field_validator("name", "backup_prefix")
    @classmethod
    def _no_unsafe_chars(cls, v: str | None) -> str | None:
        return None if v is None else _no_fs_special(v)

    @field_validator("subfolder")
    @classmethod
    def _subfolder_safe(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return v
        return _no_fs_special(v)


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
    cron_timezone: str
    enabled: bool
    retention_count: int
    compress: bool
    created_at: datetime
    updated_at: datetime


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


class NotificationCreate(BaseModel):
    name: str
    url: str
    trigger: Literal["success", "failure", "always"]
    enabled: bool = True
    message_format: str = "{status}: pfSense backup completed. {details}"
    include_instance_details: bool = True
    timeout_seconds: int = 10
    headers: dict[str, str] | None = None
    payload_template: dict[str, object] | None = None


class NotificationUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    trigger: Literal["success", "failure", "always"] | None = None
    enabled: bool | None = None
    message_format: str | None = None
    include_instance_details: bool | None = None
    timeout_seconds: int | None = None
    headers: dict[str, str] | None = None
    payload_template: dict[str, object] | None = None


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    trigger: str
    enabled: bool
    message_format: str
    include_instance_details: bool
    timeout_seconds: int
    headers: dict[str, str] | None = None
    payload_template: dict[str, object] | None = None


class BackupSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    filename_format: str
    timestamp_format: str
    directory: str


class BackupSettingsUpdate(BaseModel):
    filename_format: str | None = None
    timestamp_format: str | None = None
    directory: str | None = None


class LoggingSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    level: str
    format: str


class LoggingSettingsUpdate(BaseModel):
    level: str | None = None
    format: str | None = None


class ScheduleUpdate(BaseModel):
    cron_expression: str | None = None
    cron_timezone: str = "UTC"
    enabled: bool = True
