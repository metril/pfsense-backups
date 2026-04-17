"""Shared per-instance lock map.

Both the IPC listener (for user-triggered backups) and the scheduler
(for cron-driven backups) need to serialize concurrent backups of the
same instance. Putting the lock map behind one shared object keeps the
two code paths honest.
"""

from __future__ import annotations

import threading
from collections import defaultdict


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
