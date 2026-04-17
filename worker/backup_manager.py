"""DB-driven pfSense backup executor.

Loads instance config (and decrypts credentials) from the database, performs
the HTTP form login + config download + save + retention cleanup, writes a
Backup history row, and publishes events (started/progress/finished/failed)
to the web service via ZeroMQ.

Retention and compression are per-instance; filename/timestamp/directory
come from the singleton BackupSettings row.
"""

from __future__ import annotations

import gzip
import logging
import re
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
import urllib3
from sqlalchemy.orm import sessionmaker

from pfsense_shared.crypto import Crypto
from pfsense_shared.models import Backup, BackupSettings, Instance, Job
from pfsense_shared.schemas import (
    BackupFailed,
    BackupFinished,
    BackupProgress,
    BackupStarted,
    TestConnectionResult,
)

from .ipc_publisher import IpcPublisher
from .notifier import Notifier
from .prometheus_metrics import MetricsTimer, PrometheusMetrics

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class _InstanceSnapshot:
    """Plain-data view of an Instance row + global settings, detached from the session."""

    id: int
    name: str
    url: str
    username: str
    password: str
    subfolder: str | None
    backup_prefix: str
    verify_ssl: bool
    timeout: int
    retention_count: int
    compress: bool
    directory: str
    filename_format: str
    timestamp_format: str


@dataclass
class _SaveResult:
    path: Path
    size_bytes: int
    compressed: bool


class PfSenseBackupManager:
    def __init__(
        self,
        session_factory: sessionmaker,
        publisher: IpcPublisher,
        metrics: PrometheusMetrics,
        crypto: Crypto,
        notifier: Notifier,
        hostname: str,
    ) -> None:
        self._session_factory = session_factory
        self._publisher = publisher
        self._metrics = metrics
        self._crypto = crypto
        self._notifier = notifier
        self._hostname = hostname

    # ------------------------------------------------------------------ #
    # Public entry points
    # ------------------------------------------------------------------ #

    def backup_instance(self, instance_id: int, job_id: int) -> bool:
        """Run a backup for one instance. Returns True on success."""
        snap = self._snapshot(instance_id)
        if snap is None:
            self._fail_job(job_id, f"Instance {instance_id} not found")
            return False

        self._mark_job(job_id, status="running")
        self._publisher.publish(
            BackupStarted(
                job_id=job_id,
                instance_id=snap.id,
                instance_name=snap.name,
                ts=datetime.now(UTC),
            )
        )
        self._metrics.record_backup_attempt(snap.name)
        started_at = datetime.now(UTC)
        t0 = time.time()

        try:
            with requests.Session() as http:
                self._emit_progress(job_id, snap.id, "auth")
                if not self._authenticate(http, snap):
                    raise RuntimeError("authentication failed")

                self._emit_progress(job_id, snap.id, "download")
                content = self._download_config(http, snap)
                if content is None:
                    raise RuntimeError("config download failed")

                self._emit_progress(job_id, snap.id, "save")
                result = self._save_backup(content, snap)

                self._emit_progress(job_id, snap.id, "cleanup")
                cleaned = self._cleanup_old_backups(snap)
                if cleaned > 0:
                    self._metrics.record_files_cleaned(snap.name, cleaned)
                self._update_retained_files_count(snap)

            duration = time.time() - t0
            finished_at = datetime.now(UTC)
            self._metrics.record_backup_success(snap.name, duration)
            self._write_backup_history(
                instance_id=snap.id,
                job_id=job_id,
                started_at=started_at,
                finished_at=finished_at,
                duration=duration,
                result=result,
                success=True,
                error=None,
            )
            self._mark_job(job_id, status="success", finished_at=finished_at)
            self._publisher.publish(
                BackupFinished(
                    job_id=job_id,
                    instance_id=snap.id,
                    success=True,
                    duration_seconds=duration,
                    filename=result.path.name,
                    size_bytes=result.size_bytes,
                    ts=finished_at,
                )
            )
            log.info("Backup succeeded for %s in %.1fs", snap.name, duration)
            return True

        except Exception as exc:
            duration = time.time() - t0
            finished_at = datetime.now(UTC)
            err = str(exc)
            log.error("Backup failed for %s: %s", snap.name, err)
            self._metrics.record_backup_failure(snap.name, type(exc).__name__, duration)
            self._write_backup_history(
                instance_id=snap.id,
                job_id=job_id,
                started_at=started_at,
                finished_at=finished_at,
                duration=duration,
                result=None,
                success=False,
                error=err,
            )
            self._mark_job(job_id, status="failure", finished_at=finished_at, message=err)
            self._publisher.publish(
                BackupFailed(
                    job_id=job_id,
                    instance_id=snap.id,
                    error=err,
                    ts=finished_at,
                )
            )
            return False

    def test_connection(self, instance_id: int, job_id: int) -> bool:
        """Authenticate only — no download, no DB write. Reports result via event."""
        snap = self._snapshot(instance_id)
        if snap is None:
            self._publisher.publish(
                TestConnectionResult(
                    job_id=job_id,
                    instance_id=instance_id,
                    ok=False,
                    detail="instance not found",
                    ts=datetime.now(UTC),
                )
            )
            return False

        self._mark_job(job_id, status="running")
        try:
            with requests.Session() as http:
                ok = self._authenticate(http, snap)
            detail = "authenticated" if ok else "authentication failed"
        except Exception as exc:
            ok = False
            detail = str(exc)

        self._mark_job(
            job_id,
            status="success" if ok else "failure",
            finished_at=datetime.now(UTC),
            message=detail,
        )
        self._publisher.publish(
            TestConnectionResult(
                job_id=job_id,
                instance_id=snap.id,
                ok=ok,
                detail=detail,
                ts=datetime.now(UTC),
            )
        )
        return ok

    def backup_all(self, job_id: int) -> None:
        """Run backups for every enabled instance, then send a summary notification."""
        with self._session_factory() as s:
            instance_ids: list[int] = [
                row.id for row in s.query(Instance).filter(Instance.enabled.is_(True)).all()
            ]

        success_count = 0
        failed_names: list[str] = []
        for iid in instance_ids:
            if self.backup_instance(iid, job_id=job_id):
                success_count += 1
            else:
                with self._session_factory() as s:
                    inst = s.get(Instance, iid)
                    if inst is not None:
                        failed_names.append(inst.name)

        total = len(instance_ids)
        is_success = not failed_names
        summary = (
            f"All {total} instance(s) backed up successfully"
            if is_success
            else f"Backup completed with failures ({success_count}/{total} successful)"
        )
        try:
            with self._session_factory() as s:
                self._notifier.send(
                    s,
                    is_success=is_success,
                    details=summary,
                    failed_instances=failed_names,
                )
        except Exception as exc:
            log.error("Notifier summary send failed: %s", exc)

    # ------------------------------------------------------------------ #
    # Data loading
    # ------------------------------------------------------------------ #

    def _snapshot(self, instance_id: int) -> _InstanceSnapshot | None:
        with self._session_factory() as s:
            inst = s.get(Instance, instance_id)
            if inst is None:
                return None
            settings = s.query(BackupSettings).filter(BackupSettings.id == 1).one()
            return _InstanceSnapshot(
                id=inst.id,
                name=inst.name,
                url=inst.url,
                username=self._crypto.decrypt(inst.username_ct),
                password=self._crypto.decrypt(inst.password_ct),
                subfolder=inst.subfolder,
                backup_prefix=inst.backup_prefix,
                verify_ssl=inst.verify_ssl,
                timeout=inst.timeout_seconds,
                retention_count=inst.retention_count,
                compress=inst.compress,
                directory=settings.directory,
                filename_format=settings.filename_format,
                timestamp_format=settings.timestamp_format,
            )

    # ------------------------------------------------------------------ #
    # HTTP flow (ported from the original YAML-driven code)
    # ------------------------------------------------------------------ #

    _CSRF_RE = re.compile(r"name=['\"]__csrf_magic['\"][^>]*value=['\"]([^'\"]*)['\"]")

    def _authenticate(self, http: requests.Session, snap: _InstanceSnapshot) -> bool:
        with MetricsTimer(self._metrics, snap.name, "auth") as timer:
            login_url = urljoin(snap.url, "/index.php")
            resp = http.get(login_url, verify=snap.verify_ssl, timeout=snap.timeout)
            resp.raise_for_status()
            self._metrics.record_network_request(snap.name, "login_page", resp.status_code)

            csrf_token = None
            m = self._CSRF_RE.search(resp.text)
            if m:
                csrf_token = m.group(1)

            data = {"login": "Login", "usernamefld": snap.username, "passwordfld": snap.password}
            if csrf_token:
                data["__csrf_magic"] = csrf_token
            resp = http.post(
                login_url,
                data=data,
                verify=snap.verify_ssl,
                timeout=snap.timeout,
                allow_redirects=True,
            )
            self._metrics.record_network_request(snap.name, "login", resp.status_code)

            ok = "Dashboard" in resp.text or "logout.php" in resp.text
            self._metrics.record_auth_attempt(snap.name, ok, timer.get_duration())
            if not ok:
                log.error("Authentication failed for %s", snap.name)
            return ok

    def _download_config(self, http: requests.Session, snap: _InstanceSnapshot) -> str | None:
        with MetricsTimer(self._metrics, snap.name, "download"):
            backup_url = urljoin(snap.url, "/diag_backup.php")
            resp = http.get(backup_url, verify=snap.verify_ssl, timeout=snap.timeout)
            resp.raise_for_status()
            self._metrics.record_network_request(snap.name, "backup_page", resp.status_code)

            csrf_token = None
            m = self._CSRF_RE.search(resp.text)
            if m:
                csrf_token = m.group(1)

            data = {"download": "download", "donotbackuprrd": "yes", "backupssh": "yes"}
            if csrf_token:
                data["__csrf_magic"] = csrf_token
            resp = http.post(backup_url, data=data, verify=snap.verify_ssl, timeout=snap.timeout)
            resp.raise_for_status()
            self._metrics.record_network_request(snap.name, "backup_download", resp.status_code)

            content_type = resp.headers.get("content-type", "")
            if content_type.startswith("text/xml") or resp.text.lstrip().startswith("<?xml"):
                return resp.text
            log.error(
                "Unexpected response format from %s (content-type=%s)", snap.name, content_type
            )
            return None

    # ------------------------------------------------------------------ #
    # Filesystem: save + cleanup
    # ------------------------------------------------------------------ #

    def _instance_dir(self, snap: _InstanceSnapshot) -> Path:
        root = Path(snap.directory)
        path = root / snap.subfolder if snap.subfolder else root
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _save_backup(self, content: str, snap: _InstanceSnapshot) -> _SaveResult:
        timestamp = datetime.now().strftime(snap.timestamp_format)
        filename = snap.filename_format.format(
            prefix=snap.backup_prefix, instance_name=snap.name, timestamp=timestamp
        )
        dirpath = self._instance_dir(snap)
        xml_path = dirpath / filename
        xml_path.write_text(content, encoding="utf-8")
        original_size = xml_path.stat().st_size

        if snap.compress:
            gz_path = xml_path.with_suffix(xml_path.suffix + ".gz")
            with open(xml_path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            gz_size = gz_path.stat().st_size
            ratio = gz_size / original_size if original_size > 0 else 1.0
            self._metrics.set_compression_ratio(snap.name, ratio)
            xml_path.unlink()
            self._metrics.backup_file_size_bytes.labels(instance=snap.name).set(gz_size)
            return _SaveResult(path=gz_path, size_bytes=gz_size, compressed=True)

        self._metrics.backup_file_size_bytes.labels(instance=snap.name).set(original_size)
        return _SaveResult(path=xml_path, size_bytes=original_size, compressed=False)

    def _cleanup_old_backups(self, snap: _InstanceSnapshot) -> int:
        if snap.retention_count <= 0:
            return 0
        dirpath = self._instance_dir(snap)
        pattern = f"{snap.backup_prefix}_{snap.name}_*"
        files = sorted(dirpath.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        removed = 0
        for stale in files[snap.retention_count :]:
            try:
                stale.unlink()
                removed += 1
            except OSError as exc:
                log.error("Failed to remove stale backup %s: %s", stale, exc)
        return removed

    def _update_retained_files_count(self, snap: _InstanceSnapshot) -> None:
        dirpath = self._instance_dir(snap)
        pattern = f"{snap.backup_prefix}_{snap.name}_*"
        files = list(dirpath.glob(pattern))
        self._metrics.set_files_retained(snap.name, len(files))

    # ------------------------------------------------------------------ #
    # DB side-effects
    # ------------------------------------------------------------------ #

    def _write_backup_history(
        self,
        *,
        instance_id: int,
        job_id: int,
        started_at: datetime,
        finished_at: datetime,
        duration: float,
        result: _SaveResult | None,
        success: bool,
        error: str | None,
    ) -> None:
        with self._session_factory() as s:
            row = Backup(
                instance_id=instance_id,
                job_id=job_id,
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=duration,
                filename=result.path.name if result else "",
                path=str(result.path) if result else "",
                size_bytes=result.size_bytes if result else 0,
                compressed=result.compressed if result else False,
                success=success,
                error_message=error,
            )
            s.add(row)
            s.commit()

    def _mark_job(
        self,
        job_id: int,
        *,
        status: str,
        finished_at: datetime | None = None,
        message: str | None = None,
    ) -> None:
        with self._session_factory() as s:
            job = s.get(Job, job_id)
            if job is None:
                return
            job.status = status
            if job.started_at is None and status == "running":
                job.started_at = datetime.now(UTC)
            if finished_at is not None:
                job.finished_at = finished_at
            if message is not None:
                job.message = message
            s.commit()

    def _fail_job(self, job_id: int, message: str) -> None:
        self._mark_job(job_id, status="failure", finished_at=datetime.now(UTC), message=message)

    def _emit_progress(self, job_id: int, instance_id: int, phase: str) -> None:
        self._publisher.publish(
            BackupProgress(
                job_id=job_id,
                instance_id=instance_id,
                phase=phase,  # type: ignore[arg-type]
                ts=datetime.now(UTC),
            )
        )
