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
from pfsense_shared.log_buffer import InProcessLogHandler, LogLine
from pfsense_shared.models import Job
from pfsense_shared.settings import WorkerSettings

from .backup_manager import PfSenseBackupManager
from .instance_locks import InstanceLocks
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


def _install_log_forwarder(publisher: IpcPublisher) -> None:
    """Ship every log record to the web service via ZMQ topic ``log``.

    The in-app log viewer (web side) bridges this topic into its ring buffer
    so the browser sees worker output without needing ``docker logs``.
    """

    def sink(entry: LogLine) -> None:
        try:
            publisher.publish_raw("log", entry)
        except Exception:
            # If ZMQ is down mid-shutdown we silently drop — stderr still has it.
            pass

    handler = InProcessLogHandler(service="worker", sink=sink)
    logging.getLogger().addHandler(handler)


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
    log.info("pfsense-backups worker starting")

    engine = make_engine(settings.app_db_url)
    init_db(engine)
    session_factory = make_session_factory(engine)
    _mark_stale_jobs(session_factory)

    crypto = Crypto.from_file(settings.pfsense_backups_secret_key_file)

    metrics = get_metrics_instance(port=settings.metrics_port)
    publisher = IpcPublisher(settings.zmq_pub_bind)
    _install_log_forwarder(publisher)

    notifier = Notifier(metrics=metrics, hostname=settings.hostname)
    manager = PfSenseBackupManager(
        session_factory=session_factory,
        publisher=publisher,
        metrics=metrics,
        crypto=crypto,
        notifier=notifier,
        hostname=settings.hostname,
    )

    # C2: single shared per-instance lock map for both scheduler and listener.
    instance_locks = InstanceLocks()

    scheduler = Scheduler(
        session_factory=session_factory,
        publisher=publisher,
        run_backup=manager.backup_instance,
        instance_locks=instance_locks,
    )
    scheduler.start()

    listener = IpcListener(
        bind_url=settings.zmq_pull_bind,
        session_factory=session_factory,
        manager=manager,
        scheduler=scheduler,
        notifier=notifier,
        publisher=publisher,
        instance_locks=instance_locks,
    )
    listener.start()

    stop = threading.Event()
    # H14: heartbeat is NOT a daemon — we join it cleanly on shutdown so the
    # last PUB frame gets flushed before the publisher socket closes.
    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        args=(publisher, stop, settings.heartbeat_seconds),
        name="heartbeat",
        daemon=False,
    )
    heartbeat_thread.start()

    def _shutdown(signum, _frame) -> None:
        log.info("Signal %s received; shutting down", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    stop.wait()

    # Shutdown order matters: stop producing work first, then drain in-flight
    # commands, then close the publisher (so the listener's final events still
    # reach the web service), then the heartbeat thread.
    log.info("Shutting down scheduler")
    scheduler.shutdown()
    log.info("Shutting down IPC listener")
    listener.stop()
    log.info("Joining heartbeat thread")
    heartbeat_thread.join(timeout=max(2.0, settings.heartbeat_seconds + 1.0))
    log.info("Closing publisher")
    publisher.close()
    log.info("Bye")


if __name__ == "__main__":
    main()
