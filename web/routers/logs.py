"""Log viewer endpoints: REST snapshot + WebSocket live stream.

Backed by ``LogRing`` on ``app.state.log_ring``, which is fed by:
  (a) ``InProcessLogHandler`` attached to this process's root logger
      (web-side records), and
  (b) the ZMQ SUB bridge in ``IpcClient`` which routes worker log frames
      (topic ``"log"``) into the same ring.

Auth is enforced identically to /api/events: session cookie check done
in-router because Starlette doesn't run HTTP middleware on WS upgrades.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, status
from limits import parse as parse_limit
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

from ..dependencies import CurrentUser
from ..services.log_ring import LogLine

log = logging.getLogger(__name__)

router = APIRouter()

_ws_storage = MemoryStorage()
_ws_strategy = MovingWindowRateLimiter(_ws_storage)


def _ws_client_ip(websocket: WebSocket) -> str:
    xff = websocket.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if xff:
        return xff
    client = websocket.client
    return client.host if client else "unknown"


def _ws_rate_ok(websocket: WebSocket) -> bool:
    settings = websocket.app.state.settings
    if not settings.rate_limit_enabled:
        return True
    item = parse_limit(settings.rate_limit_ws)
    return _ws_strategy.hit(item, _ws_client_ip(websocket))


@router.get("/api/logs/history")
async def logs_history(
    request: Request, user: CurrentUser
) -> dict[str, list[LogLine]]:
    """Point-in-time ring snapshot. Useful as a fallback if WS is unavailable."""
    ring = request.app.state.log_ring
    return {"entries": ring.snapshot()}


@router.websocket("/api/logs/ws")
async def logs_ws(websocket: WebSocket) -> None:
    user = websocket.session.get("user") if "session" in websocket.scope else None
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if not _ws_rate_ok(websocket):
        log.warning("Logs WS rate limit exceeded for %s", user.get("email"))
        await websocket.close(code=1013, reason="rate limit exceeded")
        return

    ring = websocket.app.state.log_ring
    await websocket.accept()
    # Snapshot FIRST so the client renders history before the live stream.
    # Sending as one frame keeps client-side state updates cheap.
    await websocket.send_text(
        json.dumps({"type": "snapshot", "entries": ring.snapshot()}, default=str)
    )

    queue = await ring.subscribe()
    try:
        while True:
            entry = await queue.get()
            await websocket.send_text(json.dumps({"type": "log", "entry": entry}, default=str))
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log.exception("Logs WS error: %s", exc)
    finally:
        await ring.unsubscribe(queue)
