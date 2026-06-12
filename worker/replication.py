"""Off-site replication (F3): one global S3 or SFTP destination,
encrypted-by-default copies, retry sweep, verify + retrieve.

Encryption contract (the user's hard constraint): a plaintext local
backup must never land plaintext off-site. ``prepare_payload`` wraps
plaintext sources with ``encrypt_pfsense_backup`` + the dedicated
replication password — chosen over Fernet because the off-site copy is
the disaster-recovery copy: a pfSense-format blob restores directly
through diag_backup.php with just the password, while Fernet ct is
unreadable if the master key died with the host. Already-encrypted
sources upload as-is unless ``double_encrypt`` adds the outer layer
(key suffix ``.2x`` marks those so tooling never trial-decrypts).

Transports are lazy-imported so deployments without replication never
pay for boto3/paramiko.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy import select

from pfsense_shared.models import Backup, Instance, ReplicationSettings
from pfsense_shared.pfsense_crypto import (
    decrypt_pfsense_backup,
    encrypt_pfsense_backup,
)

if TYPE_CHECKING:
    from pfsense_shared.crypto import Crypto

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 8
SWEEP_INTERVAL_MINUTES = 10
ALERT_AFTER_ATTEMPTS = 3
_BACKOFF_BASE_MINUTES = 10
_BACKOFF_CAP_HOURS = 24


class ReplicationError(Exception):
    pass


class ReplicationTarget(Protocol):
    def upload(self, key: str, data: bytes) -> None: ...
    def head_size(self, key: str) -> int | None:
        """Remote object size, or None when it doesn't exist."""
        ...
    def download(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def ping(self) -> None:
        """Cheap reachability/credential check; raises on failure."""
        ...


@dataclass(frozen=True)
class ReplicationConfig:
    enabled: bool
    kind: str
    base_path: str
    encrypt_plaintext: bool
    double_encrypt: bool
    replication_password: str | None
    mirror_deletes: bool
    # Transport-specific (already decrypted).
    s3_endpoint_url: str | None = None
    s3_region: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    sftp_host: str | None = None
    sftp_port: int = 22
    sftp_username: str | None = None
    sftp_password: str | None = None
    sftp_private_key: str | None = None


def load_config(session_factory: Any, crypto: Crypto) -> ReplicationConfig | None:
    """Read + decrypt the singleton; None when replication is disabled
    or the row doesn't exist yet."""
    with session_factory() as s:
        row = s.get(ReplicationSettings, 1)
        if row is None or not row.enabled:
            return None

        def dec(ct: bytes | None) -> str | None:
            return crypto.decrypt(ct) if ct else None

        return ReplicationConfig(
            enabled=True,
            kind=row.kind,
            base_path=row.base_path.strip("/"),
            encrypt_plaintext=row.encrypt_plaintext,
            double_encrypt=row.double_encrypt,
            replication_password=dec(row.replication_password_ct),
            mirror_deletes=row.mirror_deletes,
            s3_endpoint_url=row.s3_endpoint_url,
            s3_region=row.s3_region,
            s3_bucket=row.s3_bucket,
            s3_access_key_id=row.s3_access_key_id,
            s3_secret_access_key=dec(row.s3_secret_access_key_ct),
            sftp_host=row.sftp_host,
            sftp_port=row.sftp_port,
            sftp_username=row.sftp_username,
            sftp_password=dec(row.sftp_password_ct),
            sftp_private_key=dec(row.sftp_private_key_ct),
        )


# --------------------------------------------------------------------- #
# transports
# --------------------------------------------------------------------- #


class S3Target:
    def __init__(self, cfg: ReplicationConfig) -> None:
        import boto3  # lazy — see module docstring

        if not cfg.s3_bucket:
            raise ReplicationError("S3 bucket is not configured")
        self._bucket = cfg.s3_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=cfg.s3_endpoint_url or None,
            region_name=cfg.s3_region or None,
            aws_access_key_id=cfg.s3_access_key_id,
            aws_secret_access_key=cfg.s3_secret_access_key,
        )

    def upload(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)

    def head_size(self, key: str) -> int | None:
        try:
            resp = self._client.head_object(Bucket=self._bucket, Key=key)
        except self._client.exceptions.ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                return None
            raise
        return int(resp["ContentLength"])

    def download(self, key: str) -> bytes:
        resp = self._client.get_object(Bucket=self._bucket, Key=key)
        return resp["Body"].read()  # type: ignore[no-any-return]

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def ping(self) -> None:
        self._client.head_bucket(Bucket=self._bucket)


class SftpTarget:
    def __init__(self, cfg: ReplicationConfig) -> None:
        import paramiko  # lazy

        if not cfg.sftp_host or not cfg.sftp_username:
            raise ReplicationError("SFTP host/username are not configured")
        self._paramiko = paramiko
        self._cfg = cfg

    def _connect(self) -> tuple[Any, Any]:
        cfg = self._cfg
        # The constructor guarantees host/username; assert for the type
        # checker (and as a tripwire against future refactors).
        assert cfg.sftp_host and cfg.sftp_username
        transport = self._paramiko.Transport((cfg.sftp_host, cfg.sftp_port))
        if cfg.sftp_private_key:
            pkey = self._paramiko.PKey.from_private_key(
                io.StringIO(cfg.sftp_private_key)
            )
            transport.connect(username=cfg.sftp_username, pkey=pkey)
        else:
            transport.connect(
                username=cfg.sftp_username, password=cfg.sftp_password
            )
        return transport, self._paramiko.SFTPClient.from_transport(transport)

    def _mkdirs(self, sftp: Any, key: str) -> None:
        parts = key.split("/")[:-1]
        path = ""
        for part in parts:
            path = f"{path}/{part}" if path else part
            try:
                sftp.stat(path)
            except FileNotFoundError:
                sftp.mkdir(path)

    def upload(self, key: str, data: bytes) -> None:
        transport, sftp = self._connect()
        try:
            self._mkdirs(sftp, key)
            with sftp.open(key, "wb") as fh:
                fh.write(data)
        finally:
            transport.close()

    def head_size(self, key: str) -> int | None:
        transport, sftp = self._connect()
        try:
            try:
                return int(sftp.stat(key).st_size or 0)
            except FileNotFoundError:
                return None
        finally:
            transport.close()

    def download(self, key: str) -> bytes:
        transport, sftp = self._connect()
        try:
            with sftp.open(key, "rb") as fh:
                return fh.read()  # type: ignore[no-any-return]
        finally:
            transport.close()

    def delete(self, key: str) -> None:
        transport, sftp = self._connect()
        try:
            sftp.remove(key)
        finally:
            transport.close()

    def ping(self) -> None:
        transport, _sftp = self._connect()
        transport.close()


def make_target(cfg: ReplicationConfig) -> ReplicationTarget:
    if cfg.kind == "sftp":
        return SftpTarget(cfg)
    return S3Target(cfg)


# --------------------------------------------------------------------- #
# payload preparation
# --------------------------------------------------------------------- #


def prepare_payload(
    raw: bytes, *, encrypted: bool, compressed: bool, cfg: ReplicationConfig
) -> tuple[bytes, str]:
    """(payload bytes, filename suffix) for the off-site object.

    Suffix encodes the layout so retrieve/decrypt tooling never has to
    trial-decrypt: ``.xml`` plaintext, ``.xml.enc`` one pfSense layer,
    ``.2x.xml.enc`` replication layer over an already-encrypted source.
    """
    if encrypted:
        # Source bytes may be gzipped on disk; the off-site object is
        # always the unwrapped blob (restorability beats compression —
        # the pfSense wrapper is base64, it barely compresses anyway).
        blob = gzip.decompress(raw) if compressed else raw
        if cfg.double_encrypt:
            if not cfg.replication_password:
                raise ReplicationError(
                    "double_encrypt is on but no replication password is set"
                )
            return (
                encrypt_pfsense_backup(blob, cfg.replication_password),
                ".2x.xml.enc",
            )
        return blob, ".xml.enc"

    xml = gzip.decompress(raw) if compressed else raw
    if cfg.encrypt_plaintext:
        if not cfg.replication_password:
            raise ReplicationError(
                "encrypt_plaintext is on but no replication password is set"
            )
        return encrypt_pfsense_backup(xml, cfg.replication_password), ".xml.enc"
    return xml, ".xml"


def object_key(cfg: ReplicationConfig, instance_name: str, filename: str, suffix: str) -> str:
    # Strip the local extensions; the suffix re-describes the layout.
    base = filename
    for ext in (".gz", ".xml"):
        if base.endswith(ext):
            base = base[: -len(ext)]
    return f"{cfg.base_path}/{instance_name}/{base}{suffix}"


def _undo_payload(
    payload: bytes, *, key: str, row_encrypted: bool, row_compressed: bool,
    cfg: ReplicationConfig,
) -> bytes:
    """Inverse of ``prepare_payload``: bytes ready to write back to the
    row's local path in its original on-disk shape."""
    blob = payload
    if key.endswith(".2x.xml.enc"):
        if not cfg.replication_password:
            raise ReplicationError("replication password required to strip outer layer")
        blob = decrypt_pfsense_backup(blob, cfg.replication_password)
    elif key.endswith(".xml.enc") and not row_encrypted:
        # Plaintext source that we encrypted at upload time.
        if not cfg.replication_password:
            raise ReplicationError("replication password required to decrypt replica")
        blob = decrypt_pfsense_backup(blob, cfg.replication_password)
    if row_compressed:
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            gz.write(blob)
        blob = buf.getvalue()
    return blob


# --------------------------------------------------------------------- #
# replicate / sweep / verify / retrieve
# --------------------------------------------------------------------- #


def replicate_backup(
    session_factory: Any,
    crypto: Crypto,
    backup_id: int,
    *,
    cfg: ReplicationConfig | None = None,
    target: ReplicationTarget | None = None,
) -> bool:
    """One upload attempt for one backup. Updates the row's replica
    state; never raises (the backup itself must not fail over
    replication). Returns success."""
    cfg = cfg or load_config(session_factory, crypto)
    if cfg is None:
        return False

    with session_factory() as s:
        row = s.get(Backup, backup_id)
        if row is None:
            return False
        inst = s.get(Instance, row.instance_id)
        instance_name = inst.name if inst is not None else f"instance-{row.instance_id}"
        snap = {
            "path": row.path,
            "filename": row.filename,
            "encrypted": row.encrypted,
            "compressed": row.compressed,
            "local_present": row.local_present,
        }

    def _mark(status: str, **fields: Any) -> None:
        with session_factory() as s:
            row = s.get(Backup, backup_id)
            if row is None:
                return
            row.replica_status = status
            row.replica_at = datetime.now(UTC)
            if status == "failed":
                row.replica_attempts = row.replica_attempts + 1
            for k, v in fields.items():
                setattr(row, k, v)
            s.commit()

    try:
        if not snap["local_present"]:
            raise ReplicationError("local file already pruned")
        path = Path(snap["path"])
        if not path.is_file():
            _mark("skipped", replica_error="local file missing on disk")
            return False
        raw = path.read_bytes()
        payload, suffix = prepare_payload(
            raw, encrypted=snap["encrypted"], compressed=snap["compressed"], cfg=cfg
        )
        key = object_key(cfg, instance_name, snap["filename"], suffix)
        tgt = target or make_target(cfg)
        tgt.upload(key, payload)
        # Verify before claiming success: remote size must match what
        # we sent (catches truncated puts and wrong-bucket writes).
        remote_size = tgt.head_size(key)
        if remote_size != len(payload):
            raise ReplicationError(
                f"post-upload verify failed: remote size {remote_size} "
                f"!= sent {len(payload)}"
            )
        digest = hashlib.sha256(payload).hexdigest()
        _mark("done", replica_key=key, replica_sha256=digest, replica_error=None)
        log.info("replicated backup %d → %s", backup_id, key)
        return True
    except Exception as exc:
        log.warning("replication failed for backup %d: %s", backup_id, exc)
        _mark("failed", replica_error=str(exc)[:1000])
        return False


def _attempt_due(attempts: int, last_attempt: datetime | None, now: datetime) -> bool:
    if last_attempt is None:
        return True
    if last_attempt.tzinfo is None:
        last_attempt = last_attempt.replace(tzinfo=UTC)
    backoff = min(
        timedelta(minutes=_BACKOFF_BASE_MINUTES * (2 ** max(attempts - 1, 0))),
        timedelta(hours=_BACKOFF_CAP_HOURS),
    )
    return now - last_attempt >= backoff


def sweep_pending(
    session_factory: Any,
    crypto: Crypto,
    *,
    notifier: Any | None = None,
    metrics: Any | None = None,
    now: datetime | None = None,
    target: ReplicationTarget | None = None,
) -> int:
    """Retry pass over pending/failed rows with exponential backoff.
    Returns the number of successful uploads this sweep."""
    cfg = load_config(session_factory, crypto)
    if cfg is None:
        return 0
    now = now or datetime.now(UTC)

    with session_factory() as s:
        rows = s.execute(
            select(
                Backup.id, Backup.replica_attempts, Backup.replica_at,
                Backup.replica_status, Instance.name,
            )
            .join(Instance, Instance.id == Backup.instance_id)
            .where(
                Backup.replica_status.in_(["pending", "failed"]),
                Backup.replica_attempts < MAX_ATTEMPTS,
                Backup.local_present.is_(True),
            )
        ).all()

    ok = 0
    shared_target = target or make_target(cfg)
    for bid, attempts, last_at, _status, instance_name in rows:
        if not _attempt_due(attempts, last_at, now):
            continue
        success = replicate_backup(
            session_factory, crypto, bid, cfg=cfg, target=shared_target
        )
        if success:
            ok += 1
        elif attempts + 1 == ALERT_AFTER_ATTEMPTS and notifier is not None:
            # One alert per backup as it crosses the threshold — the
            # attempts counter only passes this value once.
            try:
                with session_factory() as s:
                    notifier.send(
                        s,
                        is_success=False,
                        details=(
                            f"Off-site replication for '{instance_name}' has "
                            f"failed {ALERT_AFTER_ATTEMPTS} times "
                            f"(backup id {bid}); will keep retrying."
                        ),
                        failed_instances=[instance_name],
                        succeeded_instances=[],
                    )
            except Exception as exc:
                log.error("replication-failure notification failed: %s", exc)

    if metrics is not None:
        with session_factory() as s:
            pending = len(
                s.execute(
                    select(Backup.id).where(
                        Backup.replica_status.in_(["pending", "failed"])
                    )
                ).all()
            )
        metrics.set_replication_pending(pending)
        if ok:
            metrics.set_last_successful_replication(now.timestamp())
    return ok


def verify_replicas(
    session_factory: Any,
    crypto: Crypto,
    *,
    instance_id: int | None = None,
    deep: bool = False,
    target: ReplicationTarget | None = None,
) -> tuple[int, int]:
    """Reconcile ``done`` rows against the remote: HEAD/stat each
    object, compare size presence (and sha256 with ``deep``). Mismatch
    → flip back to ``failed`` so the sweep re-uploads and the failure
    notification fires. Returns (checked, flagged)."""
    cfg = load_config(session_factory, crypto)
    if cfg is None:
        return (0, 0)
    tgt = target or make_target(cfg)

    with session_factory() as s:
        stmt = select(Backup.id, Backup.replica_key, Backup.replica_sha256).where(
            Backup.replica_status == "done"
        )
        if instance_id is not None:
            stmt = stmt.where(Backup.instance_id == instance_id)
        rows = s.execute(stmt).all()

    checked = flagged = 0
    for bid, key, sha in rows:
        checked += 1
        problem: str | None = None
        try:
            size = tgt.head_size(key)
            if size is None:
                problem = "remote object missing"
            elif deep and sha:
                blob = tgt.download(key)
                if hashlib.sha256(blob).hexdigest() != sha:
                    problem = "remote object corrupt (sha256 mismatch)"
        except Exception as exc:
            problem = f"verify error: {exc}"
        if problem is None:
            continue
        flagged += 1
        with session_factory() as s:
            row = s.get(Backup, bid)
            if row is not None:
                row.replica_status = "failed"
                row.replica_error = problem
                s.commit()
        log.warning("verify-replicas: backup %d flagged: %s", bid, problem)
    return checked, flagged


def retrieve_replica(
    session_factory: Any,
    crypto: Crypto,
    backup_id: int,
    *,
    target: ReplicationTarget | None = None,
) -> None:
    """Bring an off-site-only backup back to local storage. Raises
    ReplicationError on any failure (caller reports via job/event)."""
    cfg = load_config(session_factory, crypto)
    if cfg is None:
        raise ReplicationError("replication is not enabled")

    with session_factory() as s:
        row = s.get(Backup, backup_id)
        if row is None:
            raise ReplicationError("backup not found")
        if row.local_present:
            return  # nothing to do
        if row.replica_status != "done" or not row.replica_key:
            raise ReplicationError("no verified off-site copy recorded")
        key, sha = row.replica_key, row.replica_sha256
        path = Path(row.path)
        row_encrypted, row_compressed = row.encrypted, row.compressed

    tgt = target or make_target(cfg)
    payload = tgt.download(key)
    if sha and hashlib.sha256(payload).hexdigest() != sha:
        raise ReplicationError("downloaded object failed sha256 verification")
    local_bytes = _undo_payload(
        payload, key=key, row_encrypted=row_encrypted,
        row_compressed=row_compressed, cfg=cfg,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(local_bytes)

    with session_factory() as s:
        row = s.get(Backup, backup_id)
        if row is not None:
            row.local_present = True
            row.size_bytes = len(local_bytes)
            s.commit()
    log.info("retrieved backup %d from %s", backup_id, key)
