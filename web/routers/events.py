"""WebSocket event stream: bridges EventBus → browser.

Authentication is enforced here (not by the HTTP middleware) because Starlette
does not run HTTP middleware on WebSocket upgrades. A3: per-IP connection
rate limiting is enforced manually via ``limits`` since slowapi's
@limiter.limit decorator is HTTP-only.
"""

from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import urlparse

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from limits import parse as parse_limit
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

log = logging.getLogger(__name__)

router = APIRouter()

# In-process WS connection tracker keyed by client IP. Separate from the
# slowapi HTTP Limiter because slowapi does not process WebSocket upgrades.
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


def _origin_ok(websocket: WebSocket) -> bool:
    """Reject cross-origin WS upgrades so a malicious site can't open a
    session-cookie-authenticated event stream from the victim's browser.

    Same-origin = scheme+host+port match. Browsers without a CORS
    requirement still send the ``Origin`` header on WS upgrades, so a
    missing header is suspicious and gets rejected too. The one exception
    is non-browser clients (curl, Python scripts running tests) which
    typically omit ``Origin``; those are allowed through only when the
    app is in dev mode.
    """
    origin = websocket.headers.get("origin")
    settings = websocket.app.state.settings
    if origin is None:
        return bool(getattr(settings, "dev_mode", False))
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    if parsed.hostname != websocket.url.hostname:
        return False
    # Port: if the URL has an explicit port, match it; otherwise accept
    # the default port for the scheme.
    if parsed.port and websocket.url.port and parsed.port != websocket.url.port:
        return False
    return True


@router.websocket("/api/events")
async def events_ws(websocket: WebSocket) -> None:
    if not _origin_ok(websocket):
        log.warning(
            "WS origin rejected: origin=%r host=%r",
            websocket.headers.get("origin"),
            websocket.url.hostname,
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Auth check using the same session cookie the HTTP side reads.
    user = websocket.session.get("user") if "session" in websocket.scope else None
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if not _ws_rate_ok(websocket):
        log.warning("WS rate limit exceeded for %s", user.get("email"))
        await websocket.close(code=1013, reason="rate limit exceeded")
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
