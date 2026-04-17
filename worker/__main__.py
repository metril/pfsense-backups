"""Worker process entrypoint.

Boots Prometheus metrics, ZMQ publisher/listener, APScheduler, and signals;
then blocks until SIGTERM/SIGINT for graceful shutdown.
"""

from __future__ import annotations

import logging
import signal
import threading
from datetime import UTC, datetime

from sqlalchemy import update

from pfsense_shared.crypto import Crypto
from pfsense_shared.db import init_db, make_engine, make_session_factory
from pfsense_shared.models import Job
from pfsense_shared.settings import WorkerSettings

from .backup_manager import PfSenseBackupManager
from .ipc_listener import IpcListener
from .ipc_publisher import IpcPublisher
from .notifier import Notifier
from .prometheus_metrics import get_metrics_instance
from .scheduler import Scheduler

log = logging.getLogger(__name__)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def _mark_stale_jobs(session_factory) -> None:
    """On boot, mark any jobs left in 'running' or 'queued' as failed.

    If the worker crashed mid-backup the row would otherwise stay running forever.
    """
    with session_factory() as s:
        stmt = (
            update(Job)
            .where(Job.status.in_(["running", "queued"]))
            .values(
                status="failure",
                finished_at=datetime.now(UTC),
                message="worker restarted during execution",
            )
        )
        s.execute(stmt)
        s.commit()


def _heartbeat_loop(publisher: IpcPublisher, stop: threading.Event, interval: float) -> None:
    while not stop.wait(interval):
        try:
            publisher.heartbeat()
        except Exception as exc:
            log.error("Heartbeat publish failed: %s", exc)


def main() -> None:
    settings = WorkerSettings()
    _configure_logging(settings.log_level)
    log.info("pfsense-backup worker starting")

    engine = make_engine(settings.app_db_url)
    init_db(engine)
    session_factory = make_session_factory(engine)
    _mark_stale_jobs(session_factory)

    crypto = Crypto.from_file(settings.pfsense_backup_secret_key_file)

    metrics = get_metrics_instance(port=settings.metrics_port)
    publisher = IpcPublisher(settings.zmq_pub_bind)

    notifier = Notifier(metrics=metrics, hostname=settings.hostname)
    manager = PfSenseBackupManager(
        session_factory=session_factory,
        publisher=publisher,
        metrics=metrics,
        crypto=crypto,
        notifier=notifier,
        hostname=settings.hostname,
    )

    scheduler = Scheduler(
        session_factory=session_factory,
        db_url=settings.app_db_url,
        publisher=publisher,
        run_backup=manager.backup_instance,
    )
    scheduler.start()

    listener = IpcListener(
        bind_url=settings.zmq_pull_bind,
        session_factory=session_factory,
        manager=manager,
        scheduler=scheduler,
        notifier=notifier,
        publisher=publisher,
    )
    listener.start()

    stop = threading.Event()
    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        args=(publisher, stop, settings.heartbeat_seconds),
        name="heartbeat",
        daemon=True,
    )
    heartbeat_thread.start()

    def _shutdown(signum, _frame) -> None:
        log.info("Signal %s received; shutting down", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    stop.wait()

    log.info("Shutting down scheduler")
    scheduler.shutdown()
    log.info("Shutting down IPC listener")
    listener.stop()
    log.info("Closing publisher")
    publisher.close()
    log.info("Bye")


if __name__ == "__main__":
    main()
