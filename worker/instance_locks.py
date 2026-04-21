"""Shared per-instance lock map + per-host concurrency semaphore.

Both the IPC listener (for user-triggered backups) and the scheduler
(for cron-driven backups) need to serialize concurrent backups of the
same instance. Putting the lock map behind one shared object keeps the
two code paths honest.

The host-level semaphore guards against a ``backup_all`` sweep
pointing 32 thread-pool workers at the same pfSense box (common on
HA-pair fleets where every ``Instance`` row shares a URL). pfSense's
default PHP session table is small; slamming all workers at one host
burns sessions and can start 503ing. Cap at 2 concurrent backups per
host so a fleet-wide sweep is still parallel across distinct boxes
but polite to any single target.

The cross-process lock (``CrossProcessInstanceLock``, v0.38.0)
extends the in-process ``InstanceLocks`` serialisation across
multiple worker processes that share the same data volume. Two
worker containers hitting the same cron tick used to race — each
would log in to pfSense, download config, and write a ``Backup``
row, producing duplicate artifacts. The file lock on
``/app/data/locks/instance-{id}.lock`` serialises them via
``fcntl.flock(LOCK_EX)``. Single-process deployments are unaffected
because ``InstanceLocks`` already serialises within-process.
"""

from __future__ import annotations

import contextlib
import fcntl
import logging
import os
import threading
import time
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger(__name__)


class InstanceLocks:
    """Thread-safe map of instance_id → threading.Lock (lazily created)."""

    def __init__(self) -> None:
        # defaultdict(Lock) plus a guard so two threads hitting a new key
        # concurrently don't race on lock creation.
        self._guard = threading.Lock()
        self._locks: dict[int, threading.Lock] = defaultdict(threading.Lock)

    def for_instance(self, instance_id: int) -> threading.Lock:
        with self._guard:
            return self._locks[instance_id]


# Concurrency ceiling per distinct pfSense host. 2 is polite for
# pfSense's default PHP session / connection limits and still lets a
# fleet sweep make meaningful parallel progress across HA pairs.
_HOST_CONCURRENCY = 2


def _host_key(url: str) -> str:
    """Normalise a URL to a hostname+port used as the semaphore key.

    Falls back to the raw URL string when ``urlparse`` can't find a
    netloc — better a pessimistic key (whole URL serves as identity)
    than silently no-op the semaphore."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        return url.lower()
    port = parsed.port
    return f"{host}:{port}" if port else host


class HostSemaphores:
    """Thread-safe map of host → BoundedSemaphore capped at N.

    Shared across the IPC listener + scheduler so a user-triggered
    backup and a cron-triggered backup against the same host count
    against the same ceiling.
    """

    def __init__(self, per_host: int = _HOST_CONCURRENCY) -> None:
        self._per_host = per_host
        self._guard = threading.Lock()
        self._sems: dict[str, threading.BoundedSemaphore] = {}

    def for_url(self, url: str) -> threading.BoundedSemaphore:
        key = _host_key(url)
        with self._guard:
            sem = self._sems.get(key)
            if sem is None:
                sem = threading.BoundedSemaphore(self._per_host)
                self._sems[key] = sem
            return sem


# Heartbeat interval (seconds) while waiting for a cross-process
# lock. Kept tight enough that operators inspecting ``docker logs``
# have a clear signal the worker is live-and-blocked rather than
# stuck in a deadlock or hung network call.
_XPROC_LOCK_HEARTBEAT_SECONDS = 5.0


class CrossProcessInstanceLock:
    """Advisory file-lock manager for per-instance serialisation
    across worker processes sharing the same data volume.

    Usage mirrors ``InstanceLocks`` — call ``for_instance(id)`` to
    get a context manager that blocks on entry until an exclusive
    ``fcntl.flock`` is acquired. Only relevant when more than one
    worker container is running against the same ``/app/data``; the
    in-process ``InstanceLocks`` already serialises within a single
    process, so single-worker deployments see no behaviour change.

    The lock file lives at ``{lock_dir}/instance-{id}.lock``. Lock
    files are created on first use with 0o600 permissions; they're
    tiny (zero bytes) and left in place after release so subsequent
    acquisitions don't need to recreate them.
    """

    def __init__(self, lock_dir: Path) -> None:
        self._lock_dir = lock_dir
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        # Protect _fd_cache from concurrent open() calls within the
        # same process. Cross-process coordination is via the OS file
        # lock itself; within-process locking handles the dict.
        self._guard = threading.Lock()
        self._fd_cache: dict[int, int] = {}

    def _path_for(self, instance_id: int) -> Path:
        return self._lock_dir / f"instance-{instance_id}.lock"

    def _fd_for(self, instance_id: int) -> int:
        with self._guard:
            fd = self._fd_cache.get(instance_id)
            if fd is not None:
                return fd
            # O_CREAT | O_RDWR — we don't write anything; the file is
            # purely a ``fcntl`` vehicle. 0o600 so the lock file can't
            # leak per-instance existence to other users on the host.
            fd = os.open(
                self._path_for(instance_id),
                os.O_CREAT | os.O_RDWR,
                0o600,
            )
            self._fd_cache[instance_id] = fd
            return fd

    @contextlib.contextmanager
    def for_instance(self, instance_id: int) -> Iterator[None]:
        """Block until we hold an exclusive lock on the per-instance
        file, then release on exit. A heartbeat log every 5s while
        blocked lets an operator distinguish "waiting politely for
        another worker" from "stuck in a deadlock or crashed pfSense
        session"."""
        fd = self._fd_for(instance_id)
        waited = False
        start = time.monotonic()
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                waited = True
                log.info(
                    "waiting for cross-process lock on instance %d "
                    "(held by another worker, waited %.1fs)",
                    instance_id,
                    time.monotonic() - start,
                )
                # Sleep the heartbeat interval, then try again.
                # ``flock`` with LOCK_EX (no NB) would block forever
                # which is fine semantically but swallows the
                # periodic log we want for diagnostics.
                time.sleep(_XPROC_LOCK_HEARTBEAT_SECONDS)
        if waited:
            log.info(
                "acquired cross-process lock on instance %d after %.1fs",
                instance_id,
                time.monotonic() - start,
            )
        try:
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError as exc:
                # LOCK_UN shouldn't fail under normal conditions; if it
                # does, the file descriptor is likely broken — log and
                # drop it from the cache so next acquire reopens.
                log.warning(
                    "failed to release cross-process lock on instance "
                    "%d: %s — reopening on next acquire",
                    instance_id,
                    exc,
                )
                with self._guard:
                    self._fd_cache.pop(instance_id, None)
                with contextlib.suppress(OSError):
                    os.close(fd)
