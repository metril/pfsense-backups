"""FastAPI app factory.

Wires session middleware, auth middleware, routers, SPA mount, and the
IPC/EventBus/OIDC singletons that requests depend on.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from pfsense_shared.crypto import Crypto
from pfsense_shared.db import (
    init_db,
    make_async_engine,
    make_async_session_factory,
    make_engine,
)
from pfsense_shared.settings import WebSettings

from .middleware import AuthRequiredMiddleware
from .routers import auth as auth_router
from .routers import backups as backups_router
from .routers import events as events_router
from .routers import health as health_router
from .routers import instances as instances_router
from .routers import jobs as jobs_router
from .routers import notifications as notifications_router
from .routers import schedule as schedule_router
from .routers import settings_router
from .services.event_bus import EventBus
from .services.ipc_client import IpcClient
from .services.oidc import make_oauth
from .services.rate_limit import configure_from_settings, limiter, rate_limit_exceeded_handler
from .static_spa import mount_spa

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: WebSettings = app.state.settings

    # Migrations + seeding run on the sync engine (Alembic's command.upgrade
    # uses a sync Connection internally; there's no async Alembic). The
    # runtime request path uses the async engine for non-blocking DB I/O.
    sync_engine = make_engine(settings.app_db_url)
    init_db(sync_engine)
    sync_engine.dispose()

    async_engine = make_async_engine(settings.app_db_url)
    app.state.engine = async_engine
    app.state.session_factory = make_async_session_factory(async_engine)
    app.state.crypto = Crypto.from_file(settings.pfsense_backups_secret_key_file)

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
        await async_engine.dispose()


def create_app(settings: WebSettings | None = None, static_dir: Path | None = None) -> FastAPI:
    settings = settings or WebSettings()

    app = FastAPI(title="pfSense Backup", lifespan=lifespan)
    app.state.settings = settings

    # A3: configure the module-level slowapi limiter with this app's settings
    # and attach it to app.state so SlowAPIMiddleware can find it.
    configure_from_settings(settings)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # Proxy-awareness BEFORE session middleware so `request.url` reflects https://.
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        # H13: flag drops in dev so http://localhost:8080 keeps the cookie.
        https_only=not settings.dev_mode,
        same_site="lax",
        max_age=14 * 24 * 3600,
    )
    app.add_middleware(AuthRequiredMiddleware)

    app.include_router(auth_router.router)
    app.include_router(health_router.router)
    app.include_router(events_router.router)
    app.include_router(instances_router.router)
    app.include_router(schedule_router.router)
    app.include_router(notifications_router.router)
    app.include_router(settings_router.router)
    app.include_router(jobs_router.router)
    app.include_router(backups_router.router)

    spa_dir = static_dir or Path(__file__).resolve().parent / "static"
    mount_spa(app, spa_dir)

    return app
