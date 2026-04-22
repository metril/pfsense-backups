"""Worker process entrypoint.

Boots Prometheus metrics, ZMQ publisher/listener, APScheduler, and signals;
then blocks until SIGTERM/SIGINT for graceful shutdown.

Subcommands (via ``python -m worker <cmd>``):

- (default) — run the worker loop described above.
- ``rotate-key`` — generate a fresh Fernet key, re-encrypt every
  stored ciphertext with it, and prune the legacy keys from the
  secret-key file. Must be run with both the worker and web service
  stopped so neither process holds a stale ``Crypto`` instance.
- ``reindex-anchor-events [--instance <id>]`` — populate the
  ``anchor_event`` table for instances that predate v0.40.0
  (``Instance.anchor_events_backfilled_at IS NULL``). Walks each
  instance's successful backups in chronological order, emits seed
  events for the first backup and diff-projected events for each
  subsequent pairing, then stamps the backfilled timestamp. Safe to
  rerun: per-instance transactional truncate-then-insert.
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import delete, select, update

from pfsense_shared.anchor_events import (
    diff_to_anchor_events,
    enumerate_anchors,
)
from pfsense_shared.backup_diff_storage import read_backup_bytes
from pfsense_shared.crypto import Crypto, ensure_keys, write_keys
from pfsense_shared.db import init_db, make_engine, make_session_factory
from pfsense_shared.log_buffer import InProcessLogHandler, LogLine
from pfsense_shared.models import AnchorEvent, Backup, Instance, Job
from pfsense_shared.pfsense_diff import diff_configs
from pfsense_shared.pfsense_parser import PfSenseParseError
from pfsense_shared.pfsense_parser import parse as parse_pfsense_xml
from pfsense_shared.settings import WorkerSettings

from .backup_manager import PfSenseBackupManager
from .instance_locks import CrossProcessInstanceLock, InstanceLocks
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
    # C2: single shared per-instance lock map for the scheduler, the IPC
    # listener, and backup_all's parallel sweep — one instance can never
    # back itself up twice concurrently regardless of trigger source.
    instance_locks = InstanceLocks()
    # v0.38.0: advisory file lock that serialises per-instance backups
    # across worker PROCESSES that share the same data volume. In a
    # single-worker deployment this has zero effect — the in-process
    # ``instance_locks`` above already covers it. Two worker containers
    # firing the same cron tick land here and one blocks on flock
    # until the other releases.
    lock_dir = Path(settings.app_db_url.replace("sqlite:///", "")).parent / "locks"
    cross_process_lock = CrossProcessInstanceLock(lock_dir)
    manager = PfSenseBackupManager(
        session_factory=session_factory,
        publisher=publisher,
        metrics=metrics,
        crypto=crypto,
        notifier=notifier,
        hostname=settings.hostname,
        instance_locks=instance_locks,
        cross_process_lock=cross_process_lock,
    )

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
        crypto=crypto,
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


def rotate_key() -> int:
    """Re-encrypt every stored ciphertext under a fresh Fernet key
    and prune the legacy keys from the secret-key file.

    Flow:
      1. Load current key(s) from the file → ``old_keys``.
      2. Generate a new key.
      3. Atomically write the file as ``[new_key, *old_keys]``.
         ``MultiFernet`` in the rotation process now accepts both.
      4. Walk every ciphertext column on ``Instance`` and ``Backup``,
         decrypting (MultiFernet tries every key) and re-encrypting
         with the new key. Commit in one transaction per chunk.
      5. Verify every newly-written ciphertext decrypts under a
         ``MultiFernet`` that ONLY knows the new key. Any failure
         halts rotation before the legacy keys are pruned.
      6. Atomically rewrite the file as ``[new_key]``.

    Returns a shell-style exit code (0 = success, non-zero = failed).
    """
    log = logging.getLogger("worker.rotate_key")
    settings = WorkerSettings()
    key_file = Path(settings.pfsense_backups_secret_key_file)

    old_keys = ensure_keys(key_file)
    log.info(
        "Loaded %d key(s) from %s (current=key[0])",
        len(old_keys),
        key_file,
    )

    new_key = Fernet.generate_key()
    transitional = [new_key, *old_keys]
    write_keys(key_file, transitional)
    log.info(
        "Wrote transitional secret-key file with %d key(s) — new key prepended",
        len(transitional),
    )

    crypto_multi = Crypto(transitional)
    crypto_new_only = Crypto(new_key)

    engine = make_engine(settings.app_db_url)
    session_factory = make_session_factory(engine)
    try:
        rotated_instance = _rotate_instance_rows(session_factory, crypto_multi, log)
        rotated_backup = _rotate_backup_rows(session_factory, crypto_multi, log)
        log.info(
            "Re-encrypted %d instance row(s) + %d backup row(s)",
            rotated_instance,
            rotated_backup,
        )

        # Verification sweep: every row that came out of step 4 must
        # decrypt under the NEW key alone. If it doesn't, the pruning
        # step below would lock the ciphertext out — bail before that.
        _verify_all_rows_decrypt(session_factory, crypto_new_only, log)
    except Exception as exc:
        log.error("Rotation failed: %s", exc, exc_info=True)
        log.error(
            "The transitional key file has been left in place. "
            "Existing ciphertexts remain decryptable via the legacy "
            "keys. Investigate and re-run rotate-key."
        )
        return 1
    finally:
        engine.dispose()

    # Pruning: new key only. Old keys drop out of the file.
    write_keys(key_file, [new_key])
    log.info(
        "Rotation complete. Secret-key file rewritten with 1 key "
        "(legacy keys dropped). Restart the worker + web service to "
        "pick up the new Crypto instance."
    )
    return 0


def _rotate_instance_rows(
    session_factory: Any, crypto: Crypto, log: logging.Logger
) -> int:
    """Walk every ``Instance`` row, decrypt its three ciphertext
    columns, re-encrypt with the new (first) key, commit. Returns
    the number of rows updated."""
    count = 0
    with session_factory() as session:
        rows = session.execute(select(Instance)).scalars().all()
        for row in rows:
            row.username_ct = crypto.encrypt(crypto.decrypt(row.username_ct))
            row.password_ct = crypto.encrypt(crypto.decrypt(row.password_ct))
            if row.backup_encrypt_password_ct is not None:
                row.backup_encrypt_password_ct = crypto.encrypt(
                    crypto.decrypt(row.backup_encrypt_password_ct)
                )
            count += 1
        session.commit()
        log.info("Instance rows re-encrypted: %d", count)
    return count


def _rotate_backup_rows(
    session_factory: Any, crypto: Crypto, log: logging.Logger
) -> int:
    """Walk every ``Backup`` row that has an ``encrypt_password_ct``.
    Commits in chunks of 500 to keep the transaction manageable for
    instances with deep history."""
    chunk = 500
    total = 0
    with session_factory() as session:
        offset = 0
        while True:
            rows = (
                session.execute(
                    select(Backup)
                    .where(Backup.encrypt_password_ct.is_not(None))
                    .order_by(Backup.id.asc())
                    .offset(offset)
                    .limit(chunk)
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for row in rows:
                assert row.encrypt_password_ct is not None  # narrowed by WHERE
                row.encrypt_password_ct = crypto.encrypt(
                    crypto.decrypt(row.encrypt_password_ct)
                )
            session.commit()
            total += len(rows)
            offset += chunk
            log.info("Backup rows re-encrypted so far: %d", total)
    return total


def _verify_all_rows_decrypt(
    session_factory: Any, crypto_new_only: Crypto, log: logging.Logger
) -> None:
    """Sanity pass: every ciphertext column we just touched must
    decrypt under a ``Crypto`` built with ONLY the new key. If any
    row fails, the pruning step would render it unreadable —
    raise and stop rotation before writing the pruned file."""
    bad: list[str] = []
    with session_factory() as session:
        for inst in session.execute(select(Instance)).scalars():
            try:
                crypto_new_only.decrypt(inst.username_ct)
                crypto_new_only.decrypt(inst.password_ct)
                if inst.backup_encrypt_password_ct is not None:
                    crypto_new_only.decrypt(inst.backup_encrypt_password_ct)
            except Exception as exc:
                bad.append(f"Instance id={inst.id}: {exc}")
        for bkp in session.execute(
            select(Backup).where(Backup.encrypt_password_ct.is_not(None))
        ).scalars():
            try:
                assert bkp.encrypt_password_ct is not None
                crypto_new_only.decrypt(bkp.encrypt_password_ct)
            except Exception as exc:
                bad.append(f"Backup id={bkp.id}: {exc}")
    if bad:
        raise RuntimeError(
            "Post-rotation verification failed for "
            f"{len(bad)} row(s): " + "; ".join(bad[:5])
        )
    log.info("Post-rotation verification OK — all rows decrypt under new key alone")


def reindex_anchor_events(instance_id: int | None = None) -> int:
    """Populate ``anchor_event`` rows for instances where the table
    is empty or partially filled (pre-v0.40.0 instances).

    Per instance:

    1. Load successful backups in ascending ``started_at`` order.
    2. Parse the first one; emit seed events (``kind='added'``,
       ``prev_backup_id=None``).
    3. Walk pairwise: diff against previous, project via
       ``diff_to_anchor_events``.
    4. Commit in a single transaction after truncating the
       instance's existing ``anchor_event`` rows — safe to rerun.
    5. Stamp ``Instance.anchor_events_backfilled_at`` on success so
       the read path flips over to the indexed surface.

    Returns shell-style exit code. Logs progress per instance; a
    single bad backup (unreadable / malformed) short-circuits that
    pair but doesn't fail the whole run — the next pair continues
    from the last good snapshot.
    """
    log = logging.getLogger("worker.reindex_anchor_events")
    settings = WorkerSettings()
    engine = make_engine(settings.app_db_url)
    init_db(engine)
    session_factory = make_session_factory(engine)
    crypto = Crypto.from_file(settings.pfsense_backups_secret_key_file)

    try:
        with session_factory() as s:
            stmt = select(Instance).where(Instance.enabled.is_(True))
            if instance_id is not None:
                stmt = stmt.where(Instance.id == instance_id)
            else:
                stmt = stmt.where(Instance.anchor_events_backfilled_at.is_(None))
            instances = s.execute(stmt).scalars().all()
            ids = [inst.id for inst in instances]

        log.info("reindex target: %d instance(s)", len(ids))
        for iid in ids:
            try:
                count = _reindex_one_instance(session_factory, iid, crypto, log)
                log.info("instance id=%d: emitted %d event(s)", iid, count)
            except Exception as exc:
                log.error("instance id=%d failed: %s", iid, exc, exc_info=True)
                # Don't abort the batch — one broken instance
                # shouldn't block the others.
                continue
        return 0
    finally:
        engine.dispose()


def _reindex_one_instance(
    session_factory: Any,
    instance_id: int,
    crypto: Crypto,
    log: logging.Logger,
) -> int:
    import json as _json

    with session_factory() as s:
        backups = (
            s.execute(
                select(Backup)
                .where(Backup.instance_id == instance_id)
                .where(Backup.success.is_(True))
                .order_by(Backup.started_at.asc())
            )
            .scalars()
            .all()
        )
        if not backups:
            log.info(
                "instance id=%d: no successful backups — marking backfilled",
                instance_id,
            )
            inst = s.get(Instance, instance_id)
            if inst is not None:
                inst.anchor_events_backfilled_at = datetime.now(UTC)
                s.commit()
            return 0

        # Truncate any existing events for this instance so rerunning
        # is idempotent. Cascade from Instance would do this too on
        # deletion, but we aren't deleting the instance.
        #
        # Crash-safety: null out ``anchor_events_backfilled_at`` in
        # the same transaction so if the process dies mid-rebuild,
        # the instance is rediscoverable by a plain
        # ``reindex-anchor-events`` re-run (which filters on
        # ``is_(None)``). Without this reset, a partial crash could
        # leave events deleted AND the flag still set from the prior
        # successful run, leading to a silent "empty history" on the
        # read path until someone passed ``--instance=`` explicitly.
        reset_inst = s.get(Instance, instance_id)
        if reset_inst is not None:
            reset_inst.anchor_events_backfilled_at = None
        s.execute(delete(AnchorEvent).where(AnchorEvent.instance_id == instance_id))
        s.flush()

        prev_parsed = None
        prev_backup_id: int | None = None
        emitted_total = 0

        for i, bkp in enumerate(backups):
            raw = read_backup_bytes(
                Path(bkp.path),
                encrypted=bkp.encrypted,
                encrypt_password_ct=bkp.encrypt_password_ct,
                crypto=crypto,
            )
            if raw is None:
                log.warning(
                    "instance id=%d: backup id=%d unreadable — skipping",
                    instance_id,
                    bkp.id,
                )
                continue
            try:
                parsed = parse_pfsense_xml(raw)
            except PfSenseParseError as exc:
                log.warning(
                    "instance id=%d: backup id=%d parse failed: %s",
                    instance_id,
                    bkp.id,
                    exc,
                )
                continue

            if prev_parsed is None:
                # First successful backup for this instance — seed.
                for anchor_id, value in enumerate_anchors(parsed):
                    s.add(
                        AnchorEvent(
                            instance_id=instance_id,
                            backup_id=bkp.id,
                            prev_backup_id=None,
                            anchor_id=anchor_id,
                            occurred_at=bkp.started_at,
                            kind="added",
                            value_json=(
                                _json.dumps(value, default=str)
                                if value is not None
                                else None
                            ),
                        )
                    )
                    emitted_total += 1
            else:
                diff = diff_configs(prev_parsed, parsed)
                for anchor_id, kind, value in diff_to_anchor_events(diff, parsed):
                    s.add(
                        AnchorEvent(
                            instance_id=instance_id,
                            backup_id=bkp.id,
                            prev_backup_id=prev_backup_id,
                            anchor_id=anchor_id,
                            occurred_at=bkp.started_at,
                            kind=kind,
                            value_json=(
                                _json.dumps(value, default=str)
                                if value is not None
                                else None
                            ),
                        )
                    )
                    emitted_total += 1

            prev_parsed = parsed
            prev_backup_id = bkp.id

            # Flush in chunks so very long histories don't hold
            # unbounded memory in the session.
            if i % 25 == 24:
                s.flush()

        inst = s.get(Instance, instance_id)
        if inst is not None:
            inst.anchor_events_backfilled_at = datetime.now(UTC)
        s.commit()
        return emitted_total


def dispatch() -> int:
    """Dispatch to a subcommand based on ``sys.argv[1]``. Returns an
    exit code. Default (no arg) runs the worker loop, which never
    returns under normal operation — wrapping it in an int return
    only matters for the ``rotate-key`` / ``reindex-anchor-events``
    paths."""
    if len(sys.argv) > 1 and sys.argv[1] == "rotate-key":
        _configure_logging("INFO")
        return rotate_key()
    if len(sys.argv) > 1 and sys.argv[1] == "reindex-anchor-events":
        _configure_logging("INFO")
        instance_id: int | None = None
        for arg in sys.argv[2:]:
            if arg.startswith("--instance="):
                instance_id = int(arg.split("=", 1)[1])
        return reindex_anchor_events(instance_id=instance_id)
    main()
    return 0


if __name__ == "__main__":
    raise SystemExit(dispatch())
