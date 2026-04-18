"""Shared logging infrastructure for the in-app log viewer.

Provides ``InProcessLogHandler``, a ``logging.Handler`` that forwards every
record to a user-supplied callback as a structured ``LogLine`` dict. The
worker uses it to publish log records over the existing ZMQ PUB socket on
topic ``"log"``; the web service uses it to fill a shared ring buffer that
``/api/logs/ws`` streams to the browser.

Wire shape (JSON-serializable, matches frontend ``LogEntry``):

    {
      "ts":       "2026-04-18T14:30:45.123456+00:00",
      "service":  "worker" | "web",
      "level":    "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL",
      "logger":   "worker.backup_manager",
      "message":  "Authentication failed for router (...)",
    }
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

LogLine = dict[str, Any]

# Loggers whose records are emitted *during* our publish path, so forwarding
# them would risk recursion / amplification. We still capture them when they
# fire for other reasons (e.g. reconnect) — just short-circuit if our
# recursion guard is active.
_RECURSION_SENTINEL = threading.local()


class InProcessLogHandler(logging.Handler):
    """Format every ``LogRecord`` as a ``LogLine`` dict and hand it to a sink.

    The handler is level-permissive (NOTSET) on its own — filtering is done
    at the root logger or by the sink — so callers get every record the
    application's log level admits.
    """

    def __init__(self, service: str, sink: Callable[[LogLine], None]) -> None:
        super().__init__(level=logging.NOTSET)
        self._service = service
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        # Guard against any re-entry: if the sink (or its downstream) ends up
        # logging while we're already inside emit on this thread, drop the
        # nested record rather than recursing forever.
        if getattr(_RECURSION_SENTINEL, "active", False):
            return
        _RECURSION_SENTINEL.active = True
        try:
            msg = record.getMessage()
            if record.exc_info:
                # Append the traceback onto the message so the viewer shows
                # the whole stack inline (rather than swallowing it).
                msg = msg + "\n" + logging.Formatter().formatException(record.exc_info)
            entry: LogLine = {
                "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
                "service": self._service,
                "level": record.levelname,
                "logger": record.name,
                "message": msg,
            }
            self._sink(entry)
        except Exception:
            # Never let a sink failure break the application's logging chain.
            # (Using handleError writes to sys.stderr via the base class.)
            self.handleError(record)
        finally:
            _RECURSION_SENTINEL.active = False
