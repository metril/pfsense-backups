"""SQLAlchemy 2.0 ORM models shared by the worker and web service."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Instance(Base):
    __tablename__ = "instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    url: Mapped[str] = mapped_column(String(512))
    username_ct: Mapped[bytes] = mapped_column(LargeBinary)
    password_ct: Mapped[bytes] = mapped_column(LargeBinary)

    subfolder: Mapped[str | None] = mapped_column(String(128), default=None, nullable=True)
    backup_prefix: Mapped[str] = mapped_column(String(64), default="daily")
    verify_ssl: Mapped[bool] = mapped_column(Boolean, default=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)

    cron_expression: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True)
    # null = inherit BackupSettings.default_timezone. A non-null string here
    # is the per-instance override the UI exposes behind a disclosure.
    cron_timezone: Mapped[str | None] = mapped_column(
        String(64), default=None, nullable=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    retention_count: Mapped[int] = mapped_column(Integer, default=365)
    compress: Mapped[bool] = mapped_column(Boolean, default=False)

    # What to pull from pfSense's diag_backup.php. Defaults mirror the old
    # hard-coded behavior so upgrades don't change what gets captured.
    backup_area: Mapped[str] = mapped_column(String(64), default="")
    backup_include_rrd: Mapped[bool] = mapped_column(Boolean, default=False)
    backup_include_packages: Mapped[bool] = mapped_column(Boolean, default=True)
    backup_include_ssh: Mapped[bool] = mapped_column(Boolean, default=True)
    backup_encrypt: Mapped[bool] = mapped_column(Boolean, default=False)
    # Fernet-encrypted (same Crypto service as password_ct); nullable when
    # the row has encryption disabled.
    backup_encrypt_password_ct: Mapped[bytes | None] = mapped_column(
        LargeBinary, default=None, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    backups: Mapped[list[Backup]] = relationship(
        back_populates="instance", cascade="all, delete-orphan"
    )


class BackupSettings(Base):
    """Singleton row (id=1) holding global file-layout settings."""

    __tablename__ = "backup_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    filename_format: Mapped[str] = mapped_column(
        String(255), default="{prefix}_{instance_name}_{timestamp}.xml"
    )
    timestamp_format: Mapped[str] = mapped_column(String(64), default="%Y-%m-%d_%H-%M-%S")
    directory: Mapped[str] = mapped_column(String(512), default="/backups")
    # Global default scheduler timezone. Applied whenever Instance.cron_timezone
    # is NULL. Consumed by worker/scheduler + web/routers/schedule.
    default_timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    # Concurrency cap for the "Backup all" sweep. Per-instance locks still
    # serialize within a single instance; this controls cross-instance fan-out.
    backup_all_max_workers: Mapped[int] = mapped_column(Integer, default=4)


class LoggingSettings(Base):
    __tablename__ = "logging_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    level: Mapped[str] = mapped_column(String(16), default="INFO")
    format: Mapped[str] = mapped_column(
        String(255), default="%(asctime)s - %(levelname)s - %(message)s"
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    # kind: discord|home_assistant|ntfy|healthchecks|webhook
    kind: Mapped[str] = mapped_column(String(32), default="webhook")
    url: Mapped[str] = mapped_column(String(1024))
    trigger: Mapped[str] = mapped_column(String(16))  # success|failure|always
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    message_format: Mapped[str] = mapped_column(
        String(512), default="{status}: pfSense backup completed. {details}"
    )
    include_instance_details: Mapped[bool] = mapped_column(Boolean, default=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10)
    headers_json: Mapped[str | None] = mapped_column(Text, default=None, nullable=True)
    payload_template_json: Mapped[str | None] = mapped_column(Text, default=None, nullable=True)
    # Kind-specific structured config (HA mode + token, ntfy priority/tags,
    # Healthchecks auto-provisioning state, etc.). NULL for kind=webhook.
    config_json: Mapped[str | None] = mapped_column(Text, default=None, nullable=True)
    # Optional per-instance scope. NULL or "[]" = all instances (default).
    instance_ids_json: Mapped[str | None] = mapped_column(Text, default=None, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("instances.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # manual|scheduled|test_connection|test_notification
    kind: Mapped[str] = mapped_column(String(32))
    requested_by: Mapped[str | None] = mapped_column(String(255), default=None, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # queued|running|success|failure|cancelled
    status: Mapped[str] = mapped_column(String(16), default="queued")
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, nullable=True
    )
    message: Mapped[str | None] = mapped_column(Text, default=None, nullable=True)


class Backup(Base):
    __tablename__ = "backups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("instances.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[float] = mapped_column(default=0.0)
    filename: Mapped[str] = mapped_column(String(512))
    path: Mapped[str] = mapped_column(String(1024))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    compressed: Mapped[bool] = mapped_column(Boolean, default=False)
    success: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, default=None, nullable=True)

    # Optional user-provided label + context so known-good backups can be
    # pinned / explained ("pre-firmware-upgrade", etc.). Both nullable;
    # retention/cleanup does not consult these.
    tag: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, default=None, nullable=True)

    # What was captured on this row — mirrors the instance's settings at
    # capture time so a later rotation of the Instance doesn't mislead us
    # about what this file actually contains.
    area: Mapped[str] = mapped_column(String(64), default="")
    included_rrd: Mapped[bool] = mapped_column(Boolean, default=False)
    included_packages: Mapped[bool] = mapped_column(Boolean, default=True)
    included_ssh: Mapped[bool] = mapped_column(Boolean, default=True)
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    # Fernet-encrypted copy of the password used for THIS backup.
    # Stored per row so rotating the instance password doesn't strand
    # older encrypted backups.
    encrypt_password_ct: Mapped[bytes | None] = mapped_column(
        LargeBinary, default=None, nullable=True
    )

    instance: Mapped[Instance] = relationship(back_populates="backups")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    actor_email: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(32))  # create|update|delete|trigger
    resource: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, default=None, nullable=True)
