"""ZeroMQ PUB socket wrapper for broadcasting worker events to the web service.

PUB sockets are not thread-safe in pyzmq, so we guard the socket with a Lock
and serialize every publish through it.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime

import zmq

from pfsense_shared.schemas import IpcEvent

log = logging.getLogger(__name__)


class IpcPublisher:
    def __init__(self, bind_url: str) -> None:
        self._ctx = zmq.Context.instance()
        self._sock: zmq.Socket[bytes] = self._ctx.socket(zmq.PUB)
        self._sock.setsockopt(zmq.LINGER, 0)
        self._sock.bind(bind_url)
        self._lock = threading.Lock()
        log.info("ZMQ PUB bound at %s", bind_url)

    def publish(self, event: IpcEvent) -> None:
        """Send an event as a multipart frame: [topic_bytes, json_bytes]."""
        topic = event.topic.encode("utf-8")
        # pydantic model_dump_json handles datetime serialization (ISO-8601).
        payload = event.model_dump_json().encode("utf-8")
        with self._lock:
            self._sock.send_multipart([topic, payload])

    def publish_raw(self, topic: str, payload: dict) -> None:
        """Escape hatch for free-form events (rarely needed; prefer typed `publish`)."""
        with self._lock:
            self._sock.send_multipart([topic.encode("utf-8"), json.dumps(payload).encode("utf-8")])

    def heartbeat(self) -> None:
        from pfsense_shared.schemas import WorkerHeartbeat

        self.publish(WorkerHeartbeat(ts=datetime.now(UTC)))

    def close(self) -> None:
        with self._lock:
            self._sock.close()
