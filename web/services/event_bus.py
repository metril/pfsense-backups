"""In-process fanout: one `put` lands in every subscribed WebSocket's queue.

Also tracks the timestamp of the most recent `worker.heartbeat` event so
`/api/health` can report whether the worker is reachable.
"""

from __future__ import annotations

import asyncio
import logging
import time

log = logging.getLogger(__name__)


class EventBus:
    def __init__(self, heartbeat_timeout: float = 15.0) -> None:
        self._subscribers: set[asyncio.Queue[dict]] = set()
        self._lock = asyncio.Lock()
        self._last_heartbeat: float = 0.0
        self._heartbeat_timeout = heartbeat_timeout

    async def publish(self, topic: str, payload: dict) -> None:
        """Fan the event out to every subscriber; swallow slow consumers rather than block."""
        envelope = {"topic": topic, **payload}
        if topic == "worker.heartbeat":
            self._last_heartbeat = time.monotonic()
        async with self._lock:
            dead: list[asyncio.Queue[dict]] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(envelope)
                except asyncio.QueueFull:
                    log.warning("WebSocket queue full, dropping client")
                    dead.append(q)
            for q in dead:
                self._subscribers.discard(q)

    async def subscribe(self) -> asyncio.Queue[dict]:
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=256)
        async with self._lock:
            self._subscribers.add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue[dict]) -> None:
        async with self._lock:
            self._subscribers.discard(q)

    def worker_alive(self) -> bool:
        """True if a heartbeat was seen within heartbeat_timeout seconds."""
        if self._last_heartbeat == 0.0:
            return False
        return (time.monotonic() - self._last_heartbeat) < self._heartbeat_timeout
