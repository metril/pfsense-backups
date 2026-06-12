"""SQLAlchemy 2.0 ORM models shared by the worker and web service."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
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

    # GFS retention tiers (F2). All NULL = pure count-based behavior
    # (the pre-F2 default — upgrades change nothing). When any tier is
    # set, the keep-set is: everything newer than ``keep_all_days``,
    # plus the newest backup per UTC day / ISO week / month within the
    # respective windows, capped at ``retention_count``. See
    # ``pfsense_shared/retention.py``.
    retention_keep_all_days: Mapped[int | None] = mapped_column(
        Integer, default=None, nullable=True
    )
    retention_daily_days: Mapped[int | None] = mapped_column(
        Integer, default=None, nullable=True
    )
    retention_weekly_weeks: Mapped[int | None] = mapped_column(
        Integer, default=None, nullable=True
    )
    retention_monthly_months: Mapped[int | None] = mapped_column(
        Integer, default=None, nullable=True
    )

    # Off-site replication opt-in (F3). The destination + credentials
    # live in the ReplicationSettings singleton; this flag just says
    # "this instance's backups go off-site".
    replicate: Mapped[bool] = mapped_column(Boolean, default=False)

    # Staleness alerting (F6). ``stale_after_hours`` NULL = auto-derive
    # from the cron cadence (2× the gap between fires, floor 1h).
    # ``stale_notified_at`` is the suppression stamp: set when a stale
    # alert fires, re-alert only after 24h, cleared (with a recovery
    # notification) by the next successful backup.
    stale_after_hours: Mapped[int | None] = mapped_column(
        Integer, default=None, nullable=True
    )
    stale_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, nullable=True
    )

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

    # v0.40.0 — once the ``anchor_event`` log has been populated for
    # every retained backup of this instance, the read path serves
    # blame / history / cumulative-changes from the indexed table.
    # NULL means "not yet backfilled" — read endpoints fall back to
    # the legacy per-request full-history walk. Set by the ingestion
    # path for newly-created instances (first-ever backup seeds the
    # events), and by the ``reindex-anchor-events`` CLI for
    # pre-existing instances.
    anchor_events_backfilled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, nullable=True
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


class ReplicationSettings(Base):
    """Singleton row (id=1): the one off-site destination (F3).

    Credentials are Fernet ciphertext (same Crypto as instance
    passwords). ``encrypt_plaintext`` (default True) wraps plaintext
    backups with ``encrypt_pfsense_backup`` + ``replication_password_ct``
    before upload — a plaintext local backup must never land plaintext
    off-site; enabling replication without a password while this is on
    is refused at the settings layer. ``double_encrypt`` additionally
    wraps already-encrypted backups in the replication-password outer
    layer (key suffix ``.2x``); default off so off-site blobs stay
    directly diag_backup.php-restorable.
    """

    __tablename__ = "replication_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    kind: Mapped[str] = mapped_column(String(16), default="s3")  # s3|sftp

    # S3 (also MinIO/R2 via endpoint_url).
    s3_endpoint_url: Mapped[str | None] = mapped_column(
        String(512), default=None, nullable=True
    )
    s3_region: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True)
    s3_bucket: Mapped[str | None] = mapped_column(String(255), default=None, nullable=True)
    s3_access_key_id: Mapped[str | None] = mapped_column(
        String(255), default=None, nullable=True
    )
    s3_secret_access_key_ct: Mapped[bytes | None] = mapped_column(
        LargeBinary, default=None, nullable=True
    )

    # SFTP.
    sftp_host: Mapped[str | None] = mapped_column(String(255), default=None, nullable=True)
    sftp_port: Mapped[int] = mapped_column(Integer, default=22)
    sftp_username: Mapped[str | None] = mapped_column(
        String(128), default=None, nullable=True
    )
    sftp_password_ct: Mapped[bytes | None] = mapped_column(
        LargeBinary, default=None, nullable=True
    )
    sftp_private_key_ct: Mapped[bytes | None] = mapped_column(
        LargeBinary, default=None, nullable=True
    )

    # Remote layout: objects land at ``{base_path}/{instance_name}/{filename}``.
    base_path: Mapped[str] = mapped_column(String(512), default="pfsense-backups")

    encrypt_plaintext: Mapped[bool] = mapped_column(Boolean, default=True)
    double_encrypt: Mapped[bool] = mapped_column(Boolean, default=False)
    replication_password_ct: Mapped[bytes | None] = mapped_column(
        LargeBinary, default=None, nullable=True
    )
    # False (default) = keep-forever off-site; retention flips rows to
    # "off-site only" instead of deleting them.
    mirror_deletes: Mapped[bool] = mapped_column(Boolean, default=False)


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
    trigger: Mapped[str] = mapped_column(String(16))  # success|failure|always|change
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
    # pfSense config SCHEMA version (the <version> tag, e.g. "23.3") —
    # set when the post-backup parse succeeds, NULL otherwise. The
    # pfSense *release* string is deliberately not captured: it isn't
    # in config.xml. Backfill for old rows: `backfill-config-versions`.
    config_version: Mapped[str | None] = mapped_column(
        String(32), default=None, nullable=True
    )

    # Off-site replication state (F3). ``replica_status``:
    #   NULL    — never eligible (instance not replicating / pre-F3 row)
    #   pending — queued for upload (retry sweep picks it up)
    #   done    — uploaded + verified; ``replica_key`` / ``replica_at``
    #             / ``replica_sha256`` describe the remote object
    #   failed  — last attempt failed; ``replica_error`` says why,
    #             ``replica_attempts`` drives the backoff
    #   skipped — permanently ineligible (e.g. file vanished locally)
    # ``local_present=False`` marks an "off-site only" row: retention
    # unlinked the local file but kept the row (and its AnchorEvents)
    # because a verified replica exists.
    replica_status: Mapped[str | None] = mapped_column(
        String(16), default=None, nullable=True
    )
    replica_key: Mapped[str | None] = mapped_column(
        String(1024), default=None, nullable=True
    )
    replica_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, nullable=True
    )
    replica_error: Mapped[str | None] = mapped_column(
        Text, default=None, nullable=True
    )
    replica_attempts: Mapped[int] = mapped_column(Integer, default=0)
    replica_sha256: Mapped[str | None] = mapped_column(
        String(64), default=None, nullable=True
    )
    local_present: Mapped[bool] = mapped_column(Boolean, default=True)
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


class ApiToken(Base):
    """Long-lived bearer token for automation (F7).

    The secret is ``pfsb_`` + 256 bits of urlsafe randomness, shown
    exactly once at creation; only its sha256 hex lands here (no salt
    needed — the secret has full entropy, so rainbow tables don't
    apply). ``prefix`` is the display handle ("pfsb_a1b2c3…").

    Scope is method-based: ``read`` = GET/HEAD only, ``write`` = all
    methods. Bearer requests skip CSRF (the header is never attached
    ambiently by a browser, which is the only thing CSRF defends
    against) but can never mint or manage tokens — that stays
    session-only.
    """

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(16))
    scope: Mapped[str] = mapped_column(String(16), default="read")  # read|write
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, nullable=True
    )


class BackupDiff(Base):
    """Precomputed structural diff between a backup and a baseline.

    Two rows per (typical) ``Backup`` exist once the v0.37.0 write
    path lands: ``kind='previous'`` against the immediately prior
    successful backup, and ``kind='first'`` against the oldest-still-
    on-disk successful backup for the same instance. Failed / missing
    base rows skip the write; lazy recompute on read covers pre-
    v0.37.0 backups.

    Cascade strategy:

    - ``ON DELETE CASCADE`` via ``backup_id`` — retention pruning
      the backup itself drops this row automatically.
    - ``ON DELETE SET NULL`` via ``base_backup_id`` — when the
      baseline gets pruned, the row survives with a NULL base and
      the read-side helper recomputes against the current baseline
      on next access, upserting over the stale row.
    """

    __tablename__ = "backup_diff"

    backup_id: Mapped[int] = mapped_column(
        ForeignKey("backups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # kind ∈ {"previous", "first"}. Checked at the DB level via
    # a CheckConstraint added in the Alembic migration (SQLite dialect
    # enforces it at row insert time).
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)

    # NULL once retention prunes the base; read path detects NULL as
    # "stale, recompute".
    base_backup_id: Mapped[int | None] = mapped_column(
        ForeignKey("backups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    added_count: Mapped[int] = mapped_column(Integer, default=0)
    removed_count: Mapped[int] = mapped_column(Integer, default=0)
    modified_count: Mapped[int] = mapped_column(Integer, default=0)
    # gzipped UTF-8 JSON of the full ConfigDiff payload. ~5-20 KB
    # typical. Reading + ungzip is cheap compared to the alternative
    # (re-parse both backups + diff them).
    full_diff_gz: Mapped[bytes] = mapped_column(LargeBinary)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class AnchorEvent(Base):
    """One row per anchor value transition in an instance's history.

    Populated at backup ingestion (and by the ``reindex-anchor-events``
    CLI for pre-existing instances). Serves three read surfaces:

    - ``/anchor-history`` — per-anchor timeline for the blame drawer.
    - ``/anchor-blame-summary`` — latest event per anchor, feeds the
      inline hover-tooltip on Structured + Raw XML views.
    - ``/cumulative-changes`` — every anchor with ≥1 event in a
      backup-range window, "original → current" collapsed.

    Change semantics:

    - ``added`` — anchor appeared in this backup (not present in
      ``prev_backup``); or the very first backup of an instance, where
      we seed one event per anchor present in the parsed config.
    - ``modified`` — anchor existed before, its serialized value
      differs now.
    - ``removed`` — anchor was present in ``prev_backup``, absent now.
      ``value_json`` carries the last-known value so the drawer can
      still show "what was deleted."
    - ``reordered`` — order-sensitive section (firewall/NAT rules)
      moved position without other field changes. ``value_json``
      carries the current row.

    Cascade strategy:

    - ``ON DELETE CASCADE`` via ``backup_id`` — retention prune drops
      the events along with the backup they describe. Matches the
      existing blame semantic ("history only covers retained
      backups").
    - ``ON DELETE SET NULL`` via ``prev_backup_id`` — pruning the
      predecessor leaves the event intact with a NULL pointer; the
      row's own existence is what matters for the index.
    """

    __tablename__ = "anchor_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("instances.id", ondelete="CASCADE"),
        nullable=False,
    )
    backup_id: Mapped[int] = mapped_column(
        ForeignKey("backups.id", ondelete="CASCADE"),
        nullable=False,
    )
    prev_backup_id: Mapped[int | None] = mapped_column(
        ForeignKey("backups.id", ondelete="SET NULL"),
        nullable=True,
    )
    anchor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # JSON-encoded post-change value. NULL for ``removed`` events when
    # we don't have a last-known-value handy (rare — the projector
    # carries ``section.removed[]`` dicts through, so ``removed``
    # events usually have a value).
    value_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # Covering index for the three read queries: blame (filter
        # by anchor_id, order by occurred_at), summary (latest per
        # anchor_id), cumulative (scan a window per anchor_id).
        Index(
            "ix_anchor_event_lookup",
            "instance_id",
            "anchor_id",
            "occurred_at",
        ),
        Index("ix_anchor_event_backup", "backup_id"),
        CheckConstraint(
            "kind in ('added','modified','removed','reordered')",
            name="ck_anchor_event_kind",
        ),
    )
