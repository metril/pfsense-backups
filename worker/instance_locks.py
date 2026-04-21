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
"""

from __future__ import annotations

import threading
from collections import defaultdict
from urllib.parse import urlparse


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
