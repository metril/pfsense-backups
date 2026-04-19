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
import os
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
import urllib3
from sqlalchemy.orm import sessionmaker

from pfsense_shared.crypto import Crypto
from pfsense_shared.models import Backup, BackupSettings, Instance, Job
from pfsense_shared.pfsense_crypto import looks_encrypted
from pfsense_shared.pfsense_probe import (
    BROWSER_HEADERS,
    DASHBOARD_MARKERS,
    LOGIN_FORM_MARKERS,
    extract_csrf,
)
from pfsense_shared.schemas import (
    BackupFailed,
    BackupFinished,
    BackupOverrides,
    BackupProgress,
    BackupStarted,
    ReencryptFinished,
    ReencryptProgress,
    ReencryptStarted,
    TestConnectionResult,
)

from .instance_locks import InstanceLocks
from .ipc_publisher import IpcPublisher
from .notifier import Notifier
from .prometheus_metrics import MetricsTimer, PrometheusMetrics

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = logging.getLogger(__name__)


def _reencrypt_one_subprocess(task: dict) -> dict:
    """Top-level subprocess worker for ProcessPoolExecutor.

    Runs inside a *spawned* interpreter — cannot touch the parent's
    ZMQ sockets, DB session, or Prometheus metrics. The parent reads
    only the returned dict and applies DB updates back on the main
    process.

    task keys: backup_id, path, compressed, old_password, new_password.
    Result keys: backup_id, ok, new_size (on success), error (on fail).
    """
    # Local imports so the parent doesn't need to pay their cost every
    # submit call and so the child picks up a clean module graph.
    import gzip
    import os
    from pathlib import Path

    from pfsense_shared.pfsense_crypto import (
        PfSenseCryptoError,
        decrypt_pfsense_backup,
        encrypt_pfsense_backup,
    )

    backup_id = task["backup_id"]
    path_str: str = task["path"]
    compressed: bool = task["compressed"]
    old_password: str = task["old_password"]
    new_password: str = task["new_password"]

    path = Path(path_str)
    try:
        # Read the file — decompress gz on the fly.
        if compressed:
            with gzip.open(path, "rb") as gz:
                raw = gz.read()
        else:
            raw = path.read_bytes()

        plaintext = decrypt_pfsense_backup(raw, old_password)
        new_wrapped = encrypt_pfsense_backup(plaintext, new_password)

        # Re-compress if the row is stored gzipped so the on-disk shape
        # doesn't flip under the user's feet.
        if compressed:
            import io
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode="wb") as gz_out:
                gz_out.write(new_wrapped)
            out_bytes = buf.getvalue()
        else:
            out_bytes = new_wrapped

        # Atomic replace via same-directory tmp so a crash mid-write
        # can't leave a truncated backup.
        tmp_path = path.with_name(f".{path.name}.tmp.{os.getpid()}")
        try:
            with open(tmp_path, "wb") as out:
                out.write(out_bytes)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp_path, path)
        except Exception:
            # Clean up the tmp on any error so we don't orphan files.
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            raise

        return {"backup_id": backup_id, "ok": True, "new_size": len(out_bytes)}
    except PfSenseCryptoError as exc:
        return {"backup_id": backup_id, "ok": False, "error": f"crypto: {exc}"}
    except FileNotFoundError:
        return {"backup_id": backup_id, "ok": False, "error": "file missing on disk"}
    except Exception as exc:
        return {"backup_id": backup_id, "ok": False, "error": str(exc)}


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

    # Backup contents — what to pull from pfSense's diag_backup.php.
    backup_area: str
    backup_include_rrd: bool
    backup_include_packages: bool
    backup_include_ssh: bool
    backup_encrypt: bool
    # Plaintext encryption password, only populated when backup_encrypt
    # is True. Decrypted from Instance.backup_encrypt_password_ct via
    # the shared Crypto service.
    backup_encrypt_password: str | None


@dataclass
class _SaveResult:
    path: Path
    size_bytes: int
    compressed: bool
    # True when the pfSense response body is the ``---- BEGIN config.xml ----``
    # encrypted wrapper rather than raw XML. When the instance asked for
    # encryption but pfSense returned plain XML (version bug, password
    # silently ignored), this is False — and ``_write_backup_history``
    # uses that to mark the row as not-actually-encrypted so subsequent
    # re-encrypt jobs don't try to decrypt plaintext.
    content_encrypted: bool


class PfSenseBackupManager:
    def __init__(
        self,
        session_factory: sessionmaker,
        publisher: IpcPublisher,
        metrics: PrometheusMetrics,
        crypto: Crypto,
        notifier: Notifier,
        hostname: str,
        instance_locks: InstanceLocks,
    ) -> None:
        self._session_factory = session_factory
        self._publisher = publisher
        self._metrics = metrics
        self._crypto = crypto
        self._notifier = notifier
        self._hostname = hostname
        self._instance_locks = instance_locks

    # ------------------------------------------------------------------ #
    # Public entry points
    # ------------------------------------------------------------------ #

    def backup_instance(
        self,
        instance_id: int,
        job_id: int,
        *,
        notify: bool = True,
        overrides: BackupOverrides | None = None,
    ) -> bool:
        """Run a backup for one instance. Returns True on success.

        ``notify=True`` (default) fires Healthchecks ``/start`` at the
        top and a per-instance terminal notification at the end, so
        manual "Backup now" and scheduled per-instance cron fires both
        alert users. ``backup_all`` passes ``notify=False`` in its
        loop and sends a single aggregate summary instead.

        ``overrides`` applies a one-shot BackupOverrides on top of the
        stored instance settings. The instance row is never mutated;
        the override only affects this run and gets captured on the
        resulting Backup row.
        """
        snap = self._snapshot(instance_id, overrides=overrides)
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

        # Surface a config-time refusal rather than hitting pfSense and
        # letting it fail with an opaque "no password" error. Defined
        # *after* ``_notify_result`` so scheduled refusals still fire
        # the configured notifications — operators must hear about this.
        if snap.backup_encrypt and not snap.backup_encrypt_password:
            msg = (
                f"Backup refused: encryption is on for '{snap.name}' but "
                f"no encryption password is configured."
            )
            self._publisher.publish(
                BackupFailed(
                    job_id=job_id,
                    instance_id=snap.id,
                    error=msg,
                    ts=datetime.now(UTC),
                )
            )
            self._fail_job(job_id, msg)
            _notify_result(False, msg)
            return False

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
                snap=snap,
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
                snap=snap,
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

    # Fallback if BackupSettings is missing a row or the value is invalid.
    # Actual parallelism is read from BackupSettings.backup_all_max_workers
    # at run time so operators can retune from the Settings page without
    # restarting the worker.
    _BACKUP_ALL_DEFAULT_WORKERS = 4
    _BACKUP_ALL_MAX_BOUND = 32

    def backup_all(
        self, job_id: int, overrides: BackupOverrides | None = None
    ) -> None:
        """Run backups for every enabled instance in parallel, then send a summary.

        ``overrides`` applies the same one-shot settings to every instance
        in the sweep. Per-instance settings stay untouched on disk.
        """
        with self._session_factory() as s:
            instance_ids: list[int] = [
                row.id for row in s.query(Instance).filter(Instance.enabled.is_(True)).all()
            ]
            settings = s.get(BackupSettings, 1)
            configured_workers = (
                settings.backup_all_max_workers
                if settings is not None
                else self._BACKUP_ALL_DEFAULT_WORKERS
            )
        # Clamp to a sane range: 1 degrades to serial (still valid), and
        # the upper bound prevents an accidentally-huge value from
        # melting the worker host or the upstream pfSense boxes.
        max_workers = max(1, min(self._BACKUP_ALL_MAX_BOUND, int(configured_workers or 1)))

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

        def _run_one(iid: int) -> tuple[int, bool]:
            # Per-instance lock serializes with user-triggered single-instance
            # backups + scheduled cron fires, so the same instance never races
            # itself. Different instances run concurrently.
            with self._instance_locks.for_instance(iid):
                ok = self.backup_instance(
                    iid, job_id=job_id, notify=False, overrides=overrides
                )
            return iid, ok

        if instance_ids:
            workers = min(max_workers, len(instance_ids))
            log.info(
                "backup_all: %d instance(s), %d parallel worker(s)",
                len(instance_ids), workers,
            )
            with ThreadPoolExecutor(
                max_workers=workers, thread_name_prefix="backup-all"
            ) as pool:
                futures = [pool.submit(_run_one, iid) for iid in instance_ids]
                for fut in as_completed(futures):
                    try:
                        iid, ok = fut.result()
                    except Exception as exc:
                        # backup_instance catches its own exceptions, so
                        # arriving here means something upstream (lock,
                        # session) blew up. Log and carry on.
                        log.error("Parallel backup task crashed: %s", exc)
                        continue
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
    # Re-encryption (per-instance + global)
    # ------------------------------------------------------------------ #

    def _reencrypt_max_workers(self) -> int:
        """Reuse the Backup-all worker cap for re-encrypt parallelism."""
        with self._session_factory() as s:
            settings = s.get(BackupSettings, 1)
        configured = (
            settings.backup_all_max_workers
            if settings is not None
            else self._BACKUP_ALL_DEFAULT_WORKERS
        )
        return max(1, min(self._BACKUP_ALL_MAX_BOUND, int(configured or 1)))

    def reencrypt_backups(self, instance_id: int, job_id: int) -> None:
        """Re-encrypt every encrypted Backup row for a single instance.

        Reads the *new* password from the already-updated Instance row
        (the web router committed it before firing this command), so
        plaintext never crosses the ZMQ wire.
        """
        self._mark_job(job_id, status="running")

        # Scope the DB session tightly: pull only the tuples we need and
        # close the session before fanning out the plaintext decrypt
        # loop. Prevents the connection from being held for the entire
        # job runtime on large fleets.
        with self._session_factory() as s:
            inst = s.get(Instance, instance_id)
            if inst is None:
                self._fail_job(job_id, f"Instance {instance_id} not found")
                return
            if not inst.backup_encrypt or not inst.backup_encrypt_password_ct:
                self._fail_job(
                    job_id,
                    f"Instance '{inst.name}' has no encryption password "
                    f"configured; nothing to re-encrypt.",
                )
                return
            new_password_ct = inst.backup_encrypt_password_ct
            instance_name = inst.name
            raw_rows = (
                s.query(
                    Backup.id, Backup.path, Backup.compressed, Backup.encrypt_password_ct
                )
                .filter(
                    Backup.instance_id == instance_id,
                    Backup.encrypted.is_(True),
                    Backup.encrypt_password_ct.is_not(None),
                )
                .order_by(Backup.id.asc())
                .all()
            )

        # Session closed. Decrypt plaintexts now.
        new_password = self._crypto.decrypt(new_password_ct)
        tasks = [
            {
                "backup_id": r.id,
                "path": r.path,
                "compressed": r.compressed,
                "old_password": self._crypto.decrypt(r.encrypt_password_ct),
                "new_password": new_password,
            }
            for r in raw_rows
        ]

        success = 0
        failure = 0
        try:
            success, failure, _ = self._reencrypt_rows(
                job_id=job_id,
                tasks=tasks,
                instance_id=instance_id,
                instance_name=instance_name,
                new_password=new_password,
            )
        finally:
            # Clear plaintext passwords from the task list promptly, and
            # always finalize the Job row so a mid-run exception doesn't
            # leave a "running" Job that the UI can't drain.
            del tasks
            self._finalize_reencrypt_job(job_id, success, failure)

    def reencrypt_all_backups(
        self,
        job_id: int,
        new_password: str,
        also_update_instance_passwords: bool,
        locked_instance_ids: set[int] | None = None,
    ) -> None:
        """Re-encrypt every encrypted Backup row across every instance.

        Optionally flips every encrypted Instance's stored password to
        ``new_password`` so future backups keep using it — done in a
        single transaction after the file work completes so a crash
        can't leave the fleet half-updated.

        ``locked_instance_ids`` is the set of instance ids the caller is
        holding per-instance locks for. When provided, the password
        rotation only touches instances in this set — a new instance
        created mid-run would be visible to the live query but its
        newly-entered password is the operator's intent for that box,
        so leaving it alone is the safe choice.
        """
        self._mark_job(job_id, status="running")
        with self._session_factory() as s:
            raw_rows = (
                s.query(
                    Backup.id, Backup.path, Backup.compressed, Backup.encrypt_password_ct
                )
                .filter(
                    Backup.encrypted.is_(True),
                    Backup.encrypt_password_ct.is_not(None),
                )
                .order_by(Backup.instance_id.asc(), Backup.id.asc())
                .all()
            )

        tasks = [
            {
                "backup_id": r.id,
                "path": r.path,
                "compressed": r.compressed,
                "old_password": self._crypto.decrypt(r.encrypt_password_ct),
                "new_password": new_password,
            }
            for r in raw_rows
        ]

        success = 0
        failure = 0
        try:
            success, failure, _ = self._reencrypt_rows(
                job_id=job_id,
                tasks=tasks,
                instance_id=None,
                instance_name=None,
                new_password=new_password,
            )

            if also_update_instance_passwords:
                try:
                    new_ct = self._crypto.encrypt(new_password)
                    with self._session_factory() as s:
                        q = s.query(Instance).filter(Instance.backup_encrypt.is_(True))
                        if locked_instance_ids is not None:
                            # Don't touch instances created after we took
                            # our lock snapshot — their password is whatever
                            # the operator just set, and we don't hold
                            # their lock to safely update it.
                            q = q.filter(Instance.id.in_(locked_instance_ids))
                        to_update = q.all()
                        for inst in to_update:
                            inst.backup_encrypt_password_ct = new_ct
                        s.commit()
                    log.info(
                        "reencrypt_all: rotated encryption password on %d instance(s)",
                        len(to_update),
                    )
                except Exception as exc:
                    log.error(
                        "reencrypt_all: instance password rotation failed: %s", exc
                    )
        finally:
            del tasks
            self._finalize_reencrypt_job(job_id, success, failure)

    def _finalize_reencrypt_job(self, job_id: int, success: int, failure: int) -> None:
        total = success + failure
        status = "success" if failure == 0 else "failure"
        if total == 0:
            msg = "No encrypted backups to re-encrypt"
        elif failure == 0:
            msg = f"Re-encrypted {success}/{total} backup(s)"
        else:
            msg = f"Re-encrypted {success}/{total} backup(s); {failure} failed"
        self._mark_job(job_id, status=status, finished_at=datetime.now(UTC), message=msg)

    def _reencrypt_rows(
        self,
        *,
        job_id: int,
        tasks: list[dict],
        instance_id: int | None,
        instance_name: str | None,
        new_password: str,
    ) -> tuple[int, int, list[dict]]:
        """Run re-encryption tasks in a ProcessPoolExecutor.

        Why processes rather than threads: pfSense's KDF (PBKDF2-SHA256
        @ 100 000 iters) runs through cryptography/CFFI which holds the
        GIL for the whole derive call. Threads would serialize; separate
        interpreters genuinely parallelize across cores.
        """
        import multiprocessing

        total = len(tasks)
        self._publisher.publish(
            ReencryptStarted(
                job_id=job_id,
                instance_id=instance_id,
                instance_name=instance_name,
                total=total,
                ts=datetime.now(UTC),
            )
        )

        failures: list[dict] = []
        success = 0
        if total == 0:
            self._publisher.publish(
                ReencryptFinished(
                    job_id=job_id,
                    instance_id=instance_id,
                    success_count=0,
                    failure_count=0,
                    failures=[],
                    ts=datetime.now(UTC),
                )
            )
            return 0, 0, []

        workers = min(self._reencrypt_max_workers(), len(tasks))
        # spawn (not fork) keeps the child out of our ZMQ context /
        # SQLAlchemy engine — both of which are not fork-safe.
        ctx = multiprocessing.get_context("spawn")
        new_password_ct_cache = self._crypto.encrypt(new_password)

        processed = 0
        with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as pool:
            future_to_task = {
                pool.submit(_reencrypt_one_subprocess, t): t for t in tasks
            }
            for fut in as_completed(future_to_task):
                task = future_to_task[fut]
                filename = os.path.basename(task["path"])
                try:
                    result = fut.result()
                except Exception as exc:
                    result = {
                        "backup_id": task["backup_id"],
                        "ok": False,
                        "error": f"subprocess crashed: {exc}",
                    }
                processed += 1
                self._publisher.publish(
                    ReencryptProgress(
                        job_id=job_id,
                        instance_id=instance_id,
                        processed=processed,
                        total=total,
                        current_backup_id=result.get("backup_id"),
                        current_filename=filename,
                        ts=datetime.now(UTC),
                    )
                )
                if result.get("ok"):
                    # Apply DB updates on the parent (child has no
                    # session). Reuse the pre-computed ciphertext so
                    # we don't re-run Fernet encrypt for every row.
                    try:
                        with self._session_factory() as s:
                            row = s.get(Backup, result["backup_id"])
                            if row is not None:
                                row.encrypt_password_ct = new_password_ct_cache
                                new_size = result.get("new_size")
                                if isinstance(new_size, int):
                                    row.size_bytes = new_size
                                s.commit()
                        success += 1
                    except Exception as exc:
                        failures.append(
                            {
                                "backup_id": task["backup_id"],
                                "filename": filename,
                                "error": f"db update failed: {exc}",
                            }
                        )
                else:
                    failures.append(
                        {
                            "backup_id": task["backup_id"],
                            "filename": filename,
                            "error": result.get("error", "unknown error"),
                        }
                    )

        self._publisher.publish(
            ReencryptFinished(
                job_id=job_id,
                instance_id=instance_id,
                success_count=success,
                failure_count=len(failures),
                failures=failures,
                ts=datetime.now(UTC),
            )
        )
        return success, len(failures), failures

    # ------------------------------------------------------------------ #
    # Data loading
    # ------------------------------------------------------------------ #

    def _snapshot(
        self, instance_id: int, overrides: BackupOverrides | None = None
    ) -> _InstanceSnapshot | None:
        with self._session_factory() as s:
            inst = s.get(Instance, instance_id)
            if inst is None:
                return None
            settings = s.query(BackupSettings).filter(BackupSettings.id == 1).one()

            # Base values come from the DB row.
            backup_area = inst.backup_area or ""
            include_rrd = inst.backup_include_rrd
            include_packages = inst.backup_include_packages
            include_ssh = inst.backup_include_ssh
            encrypt = inst.backup_encrypt
            encrypt_password: str | None = (
                self._crypto.decrypt(inst.backup_encrypt_password_ct)
                if inst.backup_encrypt and inst.backup_encrypt_password_ct
                else None
            )

            # Apply one-shot overrides on top. Each field flips only if
            # the caller explicitly set it — None means "inherit".
            if overrides is not None:
                if overrides.backup_area is not None:
                    backup_area = overrides.backup_area
                if overrides.backup_include_rrd is not None:
                    include_rrd = overrides.backup_include_rrd
                if overrides.backup_include_packages is not None:
                    include_packages = overrides.backup_include_packages
                if overrides.backup_include_ssh is not None:
                    include_ssh = overrides.backup_include_ssh
                if overrides.backup_encrypt is not None:
                    encrypt = overrides.backup_encrypt
                if overrides.backup_encrypt_password_ct is not None:
                    # Plaintext only lives in memory after this decrypt.
                    encrypt_password = self._crypto.decrypt(
                        overrides.backup_encrypt_password_ct
                    )

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
                backup_area=backup_area,
                backup_include_rrd=include_rrd,
                backup_include_packages=include_packages,
                backup_include_ssh=include_ssh,
                backup_encrypt=encrypt,
                backup_encrypt_password=encrypt_password,
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

    @staticmethod
    def build_backup_form_data(snap: _InstanceSnapshot) -> dict[str, str]:
        """Translate a snapshot's content toggles into diag_backup.php form fields.

        Separated out so unit tests can assert the wire-level payload
        without spinning up HTTP. Defaults mirror pfSense's semantics:
        ``backuparea=""`` means "Everything", the include toggles are
        expressed as their *exclusion* counterparts (``donotbackuprrd``,
        ``nopackages``) because that's how pfSense's own form posts.
        """
        data: dict[str, str] = {"download": "download"}
        # pfSense's dropdown uses "" for "Everything"; sending the key
        # explicitly is a no-op, but keeps our POST self-documenting.
        data["backuparea"] = snap.backup_area or ""
        if not snap.backup_include_rrd:
            data["donotbackuprrd"] = "yes"
        if not snap.backup_include_packages:
            data["nopackages"] = "yes"
        if snap.backup_include_ssh:
            data["backupssh"] = "yes"
        if snap.backup_encrypt and snap.backup_encrypt_password:
            data["encrypt"] = "yes"
            data["encrypt_password"] = snap.backup_encrypt_password
            data["encrypt_password_confirm"] = snap.backup_encrypt_password
        return data

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

            data = self.build_backup_form_data(snap)
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

            body = resp.text
            # When encryption is on pfSense returns the ---- BEGIN config.xml ----
            # wrapper instead of raw XML. Accept that as a valid response.
            if snap.backup_encrypt and looks_encrypted(body):
                return body
            content_type = resp.headers.get("content-type", "").lower()
            ct_ok = any(content_type.startswith(p) for p in self._XML_CONTENT_TYPE_PREFIXES)
            if ct_ok or body.lstrip().startswith("<?xml"):
                return body
            # Don't leak the whole error page (may include pfSense's
            # session cookie values); trim + single-line it.
            log.error(
                "Unexpected response format from %s (content-type=%s, first 200 chars: %s)",
                snap.name,
                content_type or "<absent>",
                body[:200].replace("\n", " "),
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

        # Probe the *actual* response shape so the DB row reflects
        # what pfSense sent, not what the operator asked for. Prevents
        # a permanently-broken re-encrypt row if pfSense ignored the
        # encrypt=yes flag (version bug, empty password silently
        # dropped) and returned plain XML instead.
        content_encrypted = looks_encrypted(content)
        if snap.backup_encrypt and not content_encrypted:
            log.warning(
                "Instance %s asked pfSense for an encrypted backup but the "
                "response body is plain XML; storing row as unencrypted.",
                snap.name,
            )

        if snap.compress:
            gz_path = xml_path.with_suffix(xml_path.suffix + ".gz")
            with open(xml_path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            gz_size = gz_path.stat().st_size
            ratio = gz_size / original_size if original_size > 0 else 1.0
            self._metrics.set_compression_ratio(snap.name, ratio)
            xml_path.unlink()
            self._metrics.backup_file_size_bytes.labels(instance=snap.name).set(gz_size)
            return _SaveResult(
                path=gz_path, size_bytes=gz_size, compressed=True,
                content_encrypted=content_encrypted,
            )

        self._metrics.backup_file_size_bytes.labels(instance=snap.name).set(original_size)
        return _SaveResult(
            path=xml_path, size_bytes=original_size, compressed=False,
            content_encrypted=content_encrypted,
        )

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
        snap: _InstanceSnapshot | None = None,
    ) -> None:
        with self._session_factory() as s:
            # Carry forward what was actually captured. When snap is None
            # (the instance disappeared before the snapshot call) we leave
            # the historical defaults in place — the migration already
            # set them to match the old hard-coded behavior.
            area = snap.backup_area if snap else ""
            included_rrd = snap.backup_include_rrd if snap else False
            included_packages = snap.backup_include_packages if snap else True
            included_ssh = snap.backup_include_ssh if snap else True
            # ``encrypted`` reflects what's actually on disk — not what we
            # asked for. If pfSense ignored encrypt=yes (version bug,
            # silently-dropped password) and returned plain XML, mark the
            # row unencrypted so later re-encrypt jobs don't try to decrypt
            # plaintext and leave the row permanently stuck as a failure.
            response_was_encrypted = bool(result and result.content_encrypted)
            encrypted = bool(
                snap and snap.backup_encrypt and success and response_was_encrypted
            )
            # Only persist the per-row password when the file on disk is
            # actually encrypted — a failed encrypt run leaves nothing
            # to decrypt, so there's no password worth storing.
            encrypt_password_ct: bytes | None = None
            if encrypted and snap is not None and snap.backup_encrypt_password:
                encrypt_password_ct = self._crypto.encrypt(snap.backup_encrypt_password)

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
                area=area,
                included_rrd=included_rrd,
                included_packages=included_packages,
                included_ssh=included_ssh,
                encrypted=encrypted,
                encrypt_password_ct=encrypt_password_ct,
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
