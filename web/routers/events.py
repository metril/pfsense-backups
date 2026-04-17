"""WebSocket event stream: bridges EventBus → browser.

Authentication is enforced here (not by the HTTP middleware) because Starlette
does not run HTTP middleware on WebSocket upgrades.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

log = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/api/events")
async def events_ws(websocket: WebSocket) -> None:
    # Auth check using the same session cookie the HTTP side reads.
    user = websocket.session.get("user") if "session" in websocket.scope else None
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    bus = websocket.app.state.event_bus
    queue = await bus.subscribe()
    await websocket.accept()
    log.info("WS connected: %s", user.get("email"))

    try:
        while True:
            event = await queue.get()
            await websocket.send_text(json.dumps(event, default=str))
    except WebSocketDisconnect:
        log.info("WS disconnected: %s", user.get("email"))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log.exception("WS error: %s", exc)
    finally:
        await bus.unsubscribe(queue)
