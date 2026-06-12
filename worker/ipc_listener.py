"""ZeroMQ PULL listener: receives commands from the web service and dispatches them.

Commands run in a small ThreadPoolExecutor so the listener loop never blocks.
A per-instance `threading.Lock` map prevents concurrent runs of the same
instance (two "Backup Now" clicks for Poseidon serialize; a click for
Poseidon + Proteus runs in parallel).
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import zmq
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from pfsense_shared.crypto import Crypto
from pfsense_shared.models import Job
from pfsense_shared.schemas import (
    NotificationSent,
    ReencryptAllBackupsCommand,
    ReencryptBackupsCommand,
    ReloadScheduleCommand,
    RunBackupAllCommand,
    RunBackupCommand,
    SendTestNotificationCommand,
    TestConnectionCommand,
)

from .backup_manager import PfSenseBackupManager
from .instance_locks import InstanceLocks
from .ipc_publisher import IpcPublisher
from .notifier import Notifier
from .scheduler import Scheduler

log = logging.getLogger(__name__)


class IpcListener:
    def __init__(
        self,
        bind_url: str,
        session_factory: sessionmaker,
        manager: PfSenseBackupManager,
        scheduler: Scheduler,
        notifier: Notifier,
        publisher: IpcPublisher,
        instance_locks: InstanceLocks,
        crypto: Crypto,
        max_workers: int = 4,
        shutdown_grace_seconds: float = 60.0,
    ) -> None:
        self._bind_url = bind_url
        self._session_factory = session_factory
        self._manager = manager
        self._scheduler = scheduler
        self._notifier = notifier
        self._publisher = publisher
        self._instance_locks = instance_locks
        self._crypto = crypto
        self._shutdown_grace_seconds = shutdown_grace_seconds

        self._ctx = zmq.Context.instance()
        self._sock: zmq.Socket[bytes] = self._ctx.socket(zmq.PULL)
        self._sock.setsockopt(zmq.LINGER, 0)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ipc-cmd")
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._sock.bind(self._bind_url)
        self._thread = threading.Thread(target=self._run_loop, name="ipc-listener", daemon=True)
        self._thread.start()
        log.info("ZMQ PULL bound at %s", self._bind_url)

    def stop(self) -> None:
        # Stop accepting new commands first.
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._sock.close()
        # Wait for in-flight commands (backups) to finish within grace.
        # H15: don't cancel mid-backup — better to let the HTTP flow finish and
        # write a proper Backup row. Past the grace window the process exit
        # will force termination anyway.
        log.info(
            "IpcListener waiting up to %.0fs for in-flight commands",
            self._shutdown_grace_seconds,
        )
        self._executor.shutdown(wait=True)

    # -------------------------------------------------------------- #
    # loop + dispatch
    # -------------------------------------------------------------- #

    def _run_loop(self) -> None:
        poller = zmq.Poller()
        poller.register(self._sock, zmq.POLLIN)
        while not self._stop.is_set():
            events = dict(poller.poll(timeout=500))
            if self._sock not in events:
                continue
            try:
                raw = self._sock.recv(flags=zmq.NOBLOCK)
            except zmq.Again:
                continue
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception as exc:
                log.error("Invalid IPC frame (not JSON): %s", exc)
                continue
            self._executor.submit(self._dispatch, payload)

    def _dispatch(self, payload: dict) -> None:
        cmd = payload.get("cmd")
        handler: Callable[[dict], None] | None = {
            "run_backup": self._handle_run_backup,
            "run_backup_all": self._handle_run_backup_all,
            "test_connection": self._handle_test_connection,
            "reload_schedule": self._handle_reload_schedule,
            "send_test_notification": self._handle_send_test_notification,
            "reencrypt_backups": self._handle_reencrypt_backups,
            "reencrypt_all_backups": self._handle_reencrypt_all_backups,
        }.get(cmd)
        if handler is None:
            log.error("Unknown IPC command: %s", cmd)
            return
        try:
            handler(payload)
        except ValidationError as exc:
            # Schema mismatch between web and worker (version skew) —
            # must be loud, and the web-created Job row must not be
            # left in "queued" until the next worker boot's
            # ``_mark_stale_jobs`` sweep.
            log.error(
                "IPC command %s failed schema validation "
                "(web/worker version skew?): %s; payload keys=%s",
                cmd, exc, sorted(payload),
            )
            self._fail_orphaned_job(payload, f"worker rejected {cmd} command: {exc}")
        except Exception as exc:  # defensive — never let a bad command kill the worker
            log.exception("Command %s failed: %s", cmd, exc)
            self._fail_orphaned_job(payload, f"{cmd} failed: {type(exc).__name__}: {exc}")

    def _fail_orphaned_job(self, payload: dict[str, Any], message: str) -> None:
        """Mark the command's Job failed if the handler died before the
        manager could. Only touches jobs still in a non-terminal state, so
        a job the handler already resolved (success or failure) keeps its
        original status and message."""
        job_id = payload.get("job_id")
        if not isinstance(job_id, int):
            return
        try:
            with self._session_factory() as s:
                job = s.get(Job, job_id)
                if job is None or job.status not in ("queued", "running"):
                    return
                job.status = "failure"
                job.finished_at = datetime.now(UTC)
                job.message = message
                s.commit()
                log.info("Marked job %d failed after command error", job_id)
        except Exception:
            log.exception("Could not mark job %s failed after command error", job_id)

    # -------------------------------------------------------------- #
    # handlers
    # -------------------------------------------------------------- #

    def _handle_run_backup(self, payload: dict) -> None:
        c = RunBackupCommand.model_validate(payload)
        with self._instance_locks.for_instance(c.instance_id):
            self._manager.backup_instance(
                c.instance_id, c.job_id, overrides=c.overrides
            )

    def _handle_run_backup_all(self, payload: dict) -> None:
        c = RunBackupAllCommand.model_validate(payload)
        self._manager.backup_all(c.job_id, overrides=c.overrides)

    def _handle_reencrypt_backups(self, payload: dict) -> None:
        c = ReencryptBackupsCommand.model_validate(payload)
        # Serialize per-instance re-encrypt with any other per-instance
        # work (scheduled backup, test connection) so a backup can't
        # race the file rewrite.
        with self._instance_locks.for_instance(c.instance_id):
            self._manager.reencrypt_backups(c.instance_id, c.job_id)

    def _handle_reencrypt_all_backups(self, payload: dict) -> None:
        c = ReencryptAllBackupsCommand.model_validate(payload)
        # Fernet-decrypt here rather than in the manager so plaintext
        # lives only in this handler's scope until the run completes.
        plaintext = self._crypto.decrypt(c.new_password_ct)

        # Serialize against every per-instance backup / reencrypt /
        # test-connection in flight. Acquire locks in sorted-id order
        # to avoid deadlock with the single-instance reencrypt path
        # (which holds exactly one lock). Each Backup.path rewrite +
        # retention-driven row delete consults the same lock, so this
        # prevents ``_cleanup_old_backups`` from deleting a row mid-
        # reencrypt or a scheduled backup from rotating the instance
        # password while we're walking it.
        from contextlib import ExitStack

        from pfsense_shared.models import Backup, Instance

        with self._session_factory() as s:
            iids = sorted(
                {
                    iid
                    for (iid,) in (
                        s.query(Instance.id)
                        .filter(Instance.backup_encrypt.is_(True))
                        .all()
                    )
                }
                | {
                    iid
                    for (iid,) in (
                        s.query(Backup.instance_id)
                        .filter(
                            Backup.encrypted.is_(True),
                            Backup.encrypt_password_ct.is_not(None),
                        )
                        .distinct()
                        .all()
                    )
                }
            )

        locked_ids = set(iids)
        with ExitStack() as stack:
            for iid in iids:
                stack.enter_context(self._instance_locks.for_instance(iid))
            self._manager.reencrypt_all_backups(
                c.job_id,
                new_password=plaintext,
                also_update_instance_passwords=c.also_update_instance_passwords,
                locked_instance_ids=locked_ids,
            )

    def _handle_test_connection(self, payload: dict) -> None:
        c = TestConnectionCommand.model_validate(payload)
        with self._instance_locks.for_instance(c.instance_id):
            self._manager.test_connection(c.instance_id, c.job_id)

    def _handle_reload_schedule(self, payload: dict) -> None:
        c = ReloadScheduleCommand.model_validate(payload)
        if c.instance_id is None:
            self._scheduler.reload_all()
        else:
            self._scheduler.reload_instance(c.instance_id)

    def _handle_send_test_notification(self, payload: dict) -> None:
        c = SendTestNotificationCommand.model_validate(payload)
        with self._session_factory() as s:
            ok, detail = self._notifier.send_test(s, c.notification_id)
        self._publisher.publish(
            NotificationSent(
                notification_id=c.notification_id,
                success=ok,
                detail=detail,
                ts=datetime.now(UTC),
            )
        )
