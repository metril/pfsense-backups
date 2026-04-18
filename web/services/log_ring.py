"""In-process log ring buffer + fanout for the web-side log viewer.

Unlike ``EventBus`` (no history), the log stream needs a **snapshot on
connect** so a fresh browser tab shows the last N lines immediately.
Implementation notes:

- ``deque(maxlen=N)`` gives O(1) append + automatic eviction of the oldest
  entry; CPython guarantees atomic append/popleft so we don't need a lock
  around the buffer itself for producer/reader races.
- Subscribers each get their own bounded ``asyncio.Queue``; on QueueFull we
  drop the subscriber (same strategy as ``EventBus``) rather than blocking
  the logging hot path.
- The producing thread may be any thread (logging handlers run wherever
  the log call happens). ``post_threadsafe`` uses ``call_soon_threadsafe``
  so the async fanout runs on the event loop it was anchored to at
  startup.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any

log = logging.getLogger(__name__)

LogLine = dict[str, Any]

_RING_CAPACITY = 1000
_QUEUE_CAPACITY = 512


class LogRing:
    def __init__(self, maxlen: int = _RING_CAPACITY) -> None:
        self._buf: deque[LogLine] = deque(maxlen=maxlen)
        self._subscribers: set[asyncio.Queue[LogLine]] = set()
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Remember the loop that ``post_threadsafe`` should marshal onto."""
        self._loop = loop

    # ---- producer side ----

    def post_threadsafe(self, entry: LogLine) -> None:
        """Called from any thread (logging.Handler.emit runs on the caller's thread)."""
        self._buf.append(entry)
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._fanout, entry)
        except RuntimeError:
            # Loop may be shutting down. Entry is still in the ring for later fetch.
            pass

    def _fanout(self, entry: LogLine) -> None:
        dead: list[asyncio.Queue[LogLine]] = []
        for q in self._subscribers:
            try:
                q.put_nowait(entry)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._subscribers.discard(q)

    # ---- consumer side ----

    def snapshot(self) -> list[LogLine]:
        """A point-in-time copy of the ring, oldest → newest."""
        return list(self._buf)

    async def subscribe(self) -> asyncio.Queue[LogLine]:
        q: asyncio.Queue[LogLine] = asyncio.Queue(maxsize=_QUEUE_CAPACITY)
        async with self._lock:
            self._subscribers.add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue[LogLine]) -> None:
        async with self._lock:
            self._subscribers.discard(q)
