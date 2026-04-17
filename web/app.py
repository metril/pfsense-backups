"""FastAPI app factory.

Wires session middleware, auth middleware, routers, SPA mount, and the
IPC/EventBus/OIDC singletons that requests depend on.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from pfsense_shared.crypto import Crypto
from pfsense_shared.db import init_db, make_engine, make_session_factory
from pfsense_shared.settings import WebSettings

from .middleware import AuthRequiredMiddleware
from .routers import auth as auth_router
from .routers import events as events_router
from .routers import health as health_router
from .services.event_bus import EventBus
from .services.ipc_client import IpcClient
from .services.oidc import make_oauth
from .static_spa import mount_spa

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: WebSettings = app.state.settings

    engine = make_engine(settings.app_db_url)
    init_db(engine)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.crypto = Crypto.from_file(settings.pfsense_backup_secret_key_file)

    bus = EventBus()
    app.state.event_bus = bus

    ipc = IpcClient(
        push_url=settings.worker_push_url,
        sub_url=settings.worker_sub_url,
        bus=bus,
    )
    ipc.start()
    app.state.ipc_client = ipc

    oauth = make_oauth(
        issuer=settings.oidc_issuer,
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
    )
    app.state.oauth = oauth

    log.info("web service ready")
    try:
        yield
    finally:
        log.info("shutting down ipc client")
        await ipc.close()


def create_app(settings: WebSettings | None = None, static_dir: Path | None = None) -> FastAPI:
    settings = settings or WebSettings()

    app = FastAPI(title="pfSense Backup", lifespan=lifespan)
    app.state.settings = settings

    # Proxy-awareness BEFORE session middleware so `request.url` reflects https://.
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        https_only=True,
        same_site="lax",
        max_age=14 * 24 * 3600,
    )
    app.add_middleware(AuthRequiredMiddleware)

    app.include_router(auth_router.router)
    app.include_router(health_router.router)
    app.include_router(events_router.router)

    spa_dir = static_dir or Path(__file__).resolve().parent / "static"
    mount_spa(app, spa_dir)

    return app
