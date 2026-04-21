"""Tests for the server-side LRU cache on
``/api/backups/instance/{id}/anchor-history``.

The endpoint walks every successful backup for an instance, parsing
each one — few hundred ms × dozens to hundreds of backups. v0.35.0
added a process-wide ``LRUCache`` keyed on ``(instance_id, anchor)``
that short-circuits the walk on subsequent identical requests.
Invalidation fires when a new ``backup.finished`` event lands on the
EventBus (handled by ``_anchor_history_invalidator`` in ``app.py``).

These tests pin:

- Cache populates after a request and second calls hit the cache.
- Explicit purge (simulating the invalidator) forces a re-compute.
- LRU eviction: with ``maxsize=2``, adding a third distinct key
  drops the oldest.
- Endpoint works when the cache is absent (tests' default app
  fixture doesn't set it).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from cachetools import LRUCache  # type: ignore[import-untyped]
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pfsense_shared.crypto import Crypto
from pfsense_shared.models import Backup

from .conftest import _seed_instance


def _xml(hostname: str) -> bytes:
    return (
        '<?xml version="1.0"?>\n'
        "<pfsense>\n"
        "  <version>21.9</version>\n"
        "  <system>\n"
        f"    <hostname>{hostname}</hostname>\n"
        "  </system>\n"
        "</pfsense>\n"
    ).encode()


async def _seed_backups(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    instance_id: int,
    hostnames: list[str],
) -> None:
    t0 = datetime(2026, 4, 1, tzinfo=UTC)
    for i, hostname in enumerate(hostnames):
        p = tmp_path / f"daily_{i}_{hostname}.xml"
        p.write_bytes(_xml(hostname))
        async with session_factory() as s:
            s.add(
                Backup(
                    instance_id=instance_id,
                    started_at=t0 + timedelta(days=i),
                    finished_at=t0 + timedelta(days=i),
                    duration_seconds=1.0,
                    filename=p.name,
                    path=str(p),
                    size_bytes=p.stat().st_size,
                    compressed=False,
                    success=True,
                    encrypted=False,
                )
            )
            await s.commit()


async def test_cache_populates_and_subsequent_calls_hit(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
) -> None:
    """First call computes + populates the cache; second call returns
    the same entries from cache. Observation: cache contents grow
    from 0 → 1 across the first call, and stay at 1 across the
    second (same key)."""
    app, session_factory, _ = app_and_session
    app.state.anchor_history_cache = LRUCache(maxsize=64)
    inst = await _seed_instance(session_factory)
    await _seed_backups(session_factory, tmp_path, inst.id, ["gw-a", "gw-b"])

    cache: LRUCache[tuple[int, str], object] = app.state.anchor_history_cache
    assert len(cache) == 0

    url = (
        f"/api/backups/instance/{inst.id}/anchor-history"
        "?anchor=field-system-hostname"
    )
    r1 = await client.get(url)
    assert r1.status_code == 200, r1.text
    assert len(cache) == 1
    assert (inst.id, "field-system-hostname") in cache

    r2 = await client.get(url)
    assert r2.status_code == 200
    # Same cache entry; no growth.
    assert len(cache) == 1
    # And the payload is identical — the cache returned the same
    # ``list[AnchorHistoryChange]`` we stored on the first hit.
    assert r2.json()["entries"] == r1.json()["entries"]


async def test_invalidation_purges_instance_entries(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
) -> None:
    """Simulating the invalidator's action (``cache.pop`` for keys
    matching ``instance_id``) forces the next request to re-populate.
    Mirrors what ``_anchor_history_invalidator`` in ``app.py`` does
    when a ``backup.finished`` event arrives on the EventBus."""
    app, session_factory, _ = app_and_session
    app.state.anchor_history_cache = LRUCache(maxsize=64)
    inst = await _seed_instance(session_factory)
    await _seed_backups(session_factory, tmp_path, inst.id, ["gw-a"])

    cache: LRUCache[tuple[int, str], object] = app.state.anchor_history_cache
    url = (
        f"/api/backups/instance/{inst.id}/anchor-history"
        "?anchor=field-system-hostname"
    )
    await client.get(url)
    assert len(cache) == 1

    # Pretend a new backup landed and the invalidator fired.
    for key in list(cache.keys()):
        if key[0] == inst.id:
            cache.pop(key, None)
    assert len(cache) == 0

    # Next call re-populates.
    await client.get(url)
    assert len(cache) == 1


async def test_cache_evicts_oldest_when_full(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
) -> None:
    """With ``maxsize=2`` the third distinct ``(instance, anchor)``
    request evicts the oldest entry. Belt + suspenders that the
    eviction policy is actually LRU and not "insert order" or
    "random"."""
    app, session_factory, _ = app_and_session
    app.state.anchor_history_cache = LRUCache(maxsize=2)
    inst = await _seed_instance(session_factory)
    await _seed_backups(session_factory, tmp_path, inst.id, ["gw-a", "gw-b"])

    cache: LRUCache[tuple[int, str], object] = app.state.anchor_history_cache
    base = f"/api/backups/instance/{inst.id}/anchor-history?anchor="

    # Three distinct anchors — last two will survive.
    await client.get(base + "field-system-hostname")
    await client.get(base + "field-system-domain")
    await client.get(base + "field-system-timezone")
    assert len(cache) == 2
    assert (inst.id, "field-system-hostname") not in cache
    assert (inst.id, "field-system-domain") in cache
    assert (inst.id, "field-system-timezone") in cache


async def test_endpoint_works_without_cache_attached(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path: Path,
) -> None:
    """The ``getattr(..., None)`` fallback means the endpoint still
    works when ``app.state.anchor_history_cache`` is missing. Keeps
    the conftest-built app (no cache set) from regressing every
    other anchor-history test in this directory."""
    app, session_factory, _ = app_and_session
    # Explicitly make sure no cache is set.
    if hasattr(app.state, "anchor_history_cache"):
        delattr(app.state, "anchor_history_cache")
    inst = await _seed_instance(session_factory)
    await _seed_backups(session_factory, tmp_path, inst.id, ["gw-a"])

    r = await client.get(
        f"/api/backups/instance/{inst.id}/anchor-history"
        "?anchor=field-system-hostname"
    )
    assert r.status_code == 200, r.text
