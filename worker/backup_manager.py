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
from pfsense_shared.pfsense_probe import (
    BROWSER_HEADERS,
    DASHBOARD_MARKERS,
    LOGIN_FORM_MARKERS,
    extract_csrf,
)
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

    def backup_instance(
        self, instance_id: int, job_id: int, *, notify: bool = True
    ) -> bool:
        """Run a backup for one instance. Returns True on success.

        ``notify=True`` (default) fires Healthchecks ``/start`` at the
        top and a per-instance terminal notification at the end, so
        manual "Backup now" and scheduled per-instance cron fires both
        alert users. ``backup_all`` passes ``notify=False`` in its
        loop and sends a single aggregate summary instead.
        """
        snap = self._snapshot(instance_id)
        if snap is None:
            self._fail_job(job_id, f"Instance {instance_id} not found")
            return False

        def _notify_result(ok: bool, detail: str) -> None:
            if not notify:
                return
            try:
                with self._session_factory() as s:
                    self._notifier.send(
                        s,
                        is_success=ok,
                        details=detail,
                        failed_instances=[] if ok else [snap.name],
                        succeeded_instances=[snap.name] if ok else [],
                    )
            except Exception as exc:
                log.error("Notifier per-instance send failed: %s", exc)

        if notify:
            try:
                with self._session_factory() as s:
                    self._notifier.ping_starts(s, instance_id=snap.id)
            except Exception as exc:
                log.warning(
                    "Healthchecks start ping for %s failed: %s", snap.name, exc
                )

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
            _notify_result(
                True,
                f"Backup succeeded for {snap.name} in {duration:.1f}s "
                f"({result.size_bytes} bytes)",
            )
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
            _notify_result(False, f"Backup failed for {snap.name}: {err}")
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

        # Fire Healthchecks /start pings before any per-instance work so
        # the check transitions to "running" in the dashboard. A failure
        # here is non-fatal — a broken endpoint must not stop backups.
        try:
            with self._session_factory() as s:
                self._notifier.ping_starts(s)
        except Exception as exc:
            log.warning("Healthchecks start pings failed: %s", exc)

        success_count = 0
        failed_names: list[str] = []
        succeeded_names: list[str] = []
        for iid in instance_ids:
            # notify=False: the aggregate summary at the bottom of this
            # method is the single notification for the sweep; per-instance
            # notifications would double-fire.
            ok = self.backup_instance(iid, job_id=job_id, notify=False)
            with self._session_factory() as s:
                inst = s.get(Instance, iid)
                if inst is None:
                    continue
                if ok:
                    success_count += 1
                    succeeded_names.append(inst.name)
                else:
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
                    succeeded_instances=succeeded_names,
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

    # Detection constants live in pfsense_shared.pfsense_probe so both this
    # module and the web service's async preflight agree on what "logged in"
    # looks like. Kept as class attrs below for back-compat with any out-of-
    # tree callers or tests that reach into them directly.
    _BROWSER_HEADERS = BROWSER_HEADERS
    _DASHBOARD_MARKERS = DASHBOARD_MARKERS
    _LOGIN_FORM_MARKERS = LOGIN_FORM_MARKERS

    # H7: pfSense emits text/xml, application/xml, or application/octet-stream
    # depending on version. Accept the family and fall back to body sniff.
    _XML_CONTENT_TYPE_PREFIXES = ("text/xml", "application/xml", "application/octet-stream")

    @classmethod
    def _extract_csrf(cls, html: str) -> str | None:
        return extract_csrf(html)

    def _authenticate(self, http: requests.Session, snap: _InstanceSnapshot) -> bool:
        with MetricsTimer(self._metrics, snap.name, "auth") as timer:
            login_url = urljoin(snap.url, "/index.php")
            resp = http.get(
                login_url,
                headers=self._BROWSER_HEADERS,
                verify=snap.verify_ssl,
                timeout=snap.timeout,
            )
            resp.raise_for_status()
            self._metrics.record_network_request(snap.name, "login_page", resp.status_code)

            csrf_token = self._extract_csrf(resp.text)
            if not csrf_token:
                log.warning(
                    "No __csrf_magic token found on login page for %s — "
                    "pfSense layout may have changed. Body starts: %s",
                    snap.name,
                    resp.text[:200].replace("\n", " ").strip(),
                )

            data = {"login": "Login", "usernamefld": snap.username, "passwordfld": snap.password}
            if csrf_token:
                data["__csrf_magic"] = csrf_token
            # Referer helps some hardened pfSense builds accept the POST.
            post_headers = {**self._BROWSER_HEADERS, "Referer": login_url}
            resp = http.post(
                login_url,
                data=data,
                headers=post_headers,
                verify=snap.verify_ssl,
                timeout=snap.timeout,
                allow_redirects=True,
            )
            self._metrics.record_network_request(snap.name, "login", resp.status_code)

            body = resp.text
            has_dashboard = any(m in body for m in self._DASHBOARD_MARKERS)
            has_login_form = any(m in body for m in self._LOGIN_FORM_MARKERS)
            # Trust the negative signal first: if the login form is still on
            # the page we're definitely not authenticated, regardless of any
            # incidental "Dashboard" text elsewhere.
            ok = has_dashboard and not has_login_form

            self._metrics.record_auth_attempt(snap.name, ok, timer.get_duration())
            cookies = ";".join(f"{c.name}" for c in http.cookies)
            if ok:
                log.info(
                    "Authentication OK for %s (final_url=%s, cookies=%s, body=%d bytes)",
                    snap.name, resp.url, cookies or "<none>", len(body),
                )
            else:
                # Dump more signal than before so the user can diagnose a
                # misidentified response (themed dashboard, MFA prompt,
                # account locked, password-expired redirect, etc.).
                snippet = body[:400].replace("\n", " ").strip()
                log.error(
                    "Authentication failed for %s "
                    "(status=%d, final_url=%s, cookies=%s, body=%d bytes, "
                    "has_dashboard=%s, has_login_form=%s, body starts: %s)",
                    snap.name, resp.status_code, resp.url, cookies or "<none>",
                    len(body), has_dashboard, has_login_form, snippet,
                )
            return ok

    def _download_config(self, http: requests.Session, snap: _InstanceSnapshot) -> str | None:
        with MetricsTimer(self._metrics, snap.name, "download"):
            backup_url = urljoin(snap.url, "/diag_backup.php")
            resp = http.get(
                backup_url,
                headers=self._BROWSER_HEADERS,
                verify=snap.verify_ssl,
                timeout=snap.timeout,
            )
            resp.raise_for_status()
            self._metrics.record_network_request(snap.name, "backup_page", resp.status_code)

            csrf_token = self._extract_csrf(resp.text)

            data = {"download": "download", "donotbackuprrd": "yes", "backupssh": "yes"}
            if csrf_token:
                data["__csrf_magic"] = csrf_token
            post_headers = {**self._BROWSER_HEADERS, "Referer": backup_url}
            resp = http.post(
                backup_url,
                data=data,
                headers=post_headers,
                verify=snap.verify_ssl,
                timeout=snap.timeout,
            )
            resp.raise_for_status()
            self._metrics.record_network_request(snap.name, "backup_download", resp.status_code)

            content_type = resp.headers.get("content-type", "").lower()
            ct_ok = any(content_type.startswith(p) for p in self._XML_CONTENT_TYPE_PREFIXES)
            if ct_ok or resp.text.lstrip().startswith("<?xml"):
                return resp.text
            log.error(
                "Unexpected response format from %s (content-type=%s, first 100 chars: %s)",
                snap.name,
                content_type or "<absent>",
                resp.text[:100].replace("\n", " "),
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
        """Retention enforcement, Backup-table-driven.

        C3/M4: previously this walked the filesystem with a glob pattern
        keyed on ``name``, which (1) orphaned DB rows after cleanup and
        (2) broke when ``name`` or ``backup_prefix`` changed. We now
        authoritatively select from the ``backups`` table, keep the most
        recent ``retention_count`` successful rows per instance, and unlink
        + delete both file and row for the rest in a single transaction.
        """
        if snap.retention_count <= 0:
            return 0

        from pfsense_shared.models import Backup  # local import to avoid cycle

        removed = 0
        with self._session_factory() as s:
            successful = (
                s.query(Backup)
                .filter(Backup.instance_id == snap.id, Backup.success.is_(True))
                .order_by(Backup.started_at.desc())
                .all()
            )
            stale_rows = successful[snap.retention_count :]
            for row in stale_rows:
                path = Path(row.path) if row.path else None
                if path is not None and path.is_file():
                    try:
                        path.unlink()
                    except OSError as exc:
                        log.error("Failed to remove stale backup %s: %s", path, exc)
                        # Still delete the row — the file pointer is dangling
                        # anyway. Err on the side of DB/FS agreement.
                s.delete(row)
                removed += 1
            if removed:
                s.commit()
        return removed

    def _update_retained_files_count(self, snap: _InstanceSnapshot) -> None:
        from pfsense_shared.models import Backup  # local import to avoid cycle

        with self._session_factory() as s:
            count = (
                s.query(Backup)
                .filter(Backup.instance_id == snap.id, Backup.success.is_(True))
                .count()
            )
        self._metrics.set_files_retained(snap.name, count)

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
