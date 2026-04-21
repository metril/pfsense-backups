"""Tests for the per-instance lock map + per-host concurrency
semaphore in ``worker.instance_locks``.

The semaphore is the load-bearing piece: a ``backup_all`` sweep of
a fleet whose instances all point at the same HA pair must be
capped at N concurrent against any one URL. These tests pin both
the keying behaviour (same hostname regardless of path / query /
scheme port) and the cap itself.
"""

from __future__ import annotations

import threading
import time

from worker.instance_locks import (
    HostSemaphores,
    InstanceLocks,
    _host_key,
)


def test_instance_lock_same_id_returns_same_lock() -> None:
    locks = InstanceLocks()
    a = locks.for_instance(42)
    b = locks.for_instance(42)
    assert a is b


def test_instance_lock_different_ids_are_independent() -> None:
    locks = InstanceLocks()
    a = locks.for_instance(1)
    b = locks.for_instance(2)
    assert a is not b


def test_host_key_normalises_scheme_and_path() -> None:
    """The semaphore must cap per HOST, not per URL. Different paths,
    query strings, and schemes on the same hostname share one key;
    different ports are separate keys (different listening services
    on the same box are usually independent pfSense installs)."""
    base = _host_key("https://pf01.example/diag_backup.php")
    assert _host_key("https://pf01.example/") == base
    assert _host_key("http://pf01.example") == base
    assert _host_key("https://pf01.example/foo?bar=1") == base
    assert _host_key("HTTPS://PF01.EXAMPLE/") == base
    # Explicit non-default port → different key.
    assert _host_key("https://pf01.example:8443/") != base
    # Different host → different key.
    assert _host_key("https://pf02.example/") != base


def test_host_key_falls_back_on_malformed_url() -> None:
    """If ``urlparse`` can't find a hostname, the whole URL is used
    as the key. Pessimistic — two bad URLs never accidentally share
    a cap."""
    assert _host_key("not-a-url") == "not-a-url"
    # Case-lowered so two casings of the same broken string still
    # share.
    assert _host_key("not-a-url") == _host_key("NOT-A-URL")


def test_host_semaphores_cap_concurrent_acquires() -> None:
    """With per_host=2, a third thread trying to acquire the same
    host's semaphore must block until one of the first two releases.
    Two different hosts never contend with each other."""
    sems = HostSemaphores(per_host=2)
    started = threading.Event()
    release = threading.Event()
    hits: list[int] = []

    def worker() -> None:
        sem = sems.for_url("https://pf01.example/")
        with sem:
            hits.append(1)
            started.set()
            # Hold the semaphore until the test says release.
            release.wait(timeout=5)

    # Fire two threads — both should acquire immediately and push
    # hits to 2.
    t1 = threading.Thread(target=worker, daemon=True)
    t2 = threading.Thread(target=worker, daemon=True)
    t1.start()
    t2.start()

    # Wait for both to be holding the semaphore.
    # (``started`` is set after the first thread, so poll len(hits).)
    deadline = time.time() + 2.0
    while len(hits) < 2 and time.time() < deadline:
        time.sleep(0.01)
    assert len(hits) == 2

    # Third thread on the same host blocks.
    t3 = threading.Thread(target=worker, daemon=True)
    t3.start()
    time.sleep(0.1)
    assert len(hits) == 2, "t3 should still be blocked on the semaphore"

    # A fourth thread on a DIFFERENT host proceeds immediately.
    other_hits: list[int] = []
    other_release = threading.Event()

    def other_worker() -> None:
        sem = sems.for_url("https://pf02.example/")
        with sem:
            other_hits.append(1)
            other_release.wait(timeout=5)

    t4 = threading.Thread(target=other_worker, daemon=True)
    t4.start()
    deadline = time.time() + 2.0
    while not other_hits and time.time() < deadline:
        time.sleep(0.01)
    assert other_hits == [1], "different hosts shouldn't contend"

    # Release everyone so the daemon threads don't leak.
    release.set()
    other_release.set()
    for t in (t1, t2, t3, t4):
        t.join(timeout=5)

    # After release, the third thread got through.
    assert len(hits) == 3
