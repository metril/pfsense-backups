"""FastAPI app factory.

Wires session middleware, auth middleware, routers, SPA mount, and the
IPC/EventBus/OIDC singletons that requests depend on.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
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
from pfsense_shared.log_buffer import InProcessLogHandler
from pfsense_shared.settings import WebSettings

from .middleware import AuthRequiredMiddleware
from .routers import audit as audit_router
from .routers import auth as auth_router
from .routers import backups as backups_router
from .routers import events as events_router
from .routers import health as health_router
from .routers import instances as instances_router
from .routers import jobs as jobs_router
from .routers import logs as logs_router
from .routers import notifications as notifications_router
from .routers import schedule as schedule_router
from .routers import settings_router
from .services.event_bus import EventBus
from .services.ipc_client import IpcClient
from .services.log_ring import LogRing
from .services.oidc import make_oidc_provider
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

    # Ring buffer for the in-app log viewer. The root logger handler we
    # install below feeds it with web-side records, and the ZMQ SUB bridge
    # routes worker log frames (topic "log") into the same ring so the
    # browser sees both services interleaved on /logs.
    log_ring = LogRing()
    log_ring.attach_loop(asyncio.get_running_loop())
    app.state.log_ring = log_ring

    web_log_handler = InProcessLogHandler(
        service="web", sink=log_ring.post_threadsafe
    )
    logging.getLogger().addHandler(web_log_handler)
    app.state.web_log_handler = web_log_handler

    ipc = IpcClient(
        push_url=settings.worker_push_url,
        sub_url=settings.worker_sub_url,
        bus=bus,
        log_ring=log_ring,
    )
    ipc.start()
    app.state.ipc_client = ipc

    app.state.oidc_provider = make_oidc_provider(
        issuer=settings.oidc_issuer,
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
    )

    log.info("web service ready")
    try:
        yield
    finally:
        log.info("shutting down ipc client")
        logging.getLogger().removeHandler(web_log_handler)
        await ipc.close()
        await async_engine.dispose()


def create_app(settings: WebSettings | None = None, static_dir: Path | None = None) -> FastAPI:
    settings = settings or WebSettings()

    app = FastAPI(title="pfSense Backups", lifespan=lifespan)
    app.state.settings = settings

    # A3: configure the module-level slowapi limiter with this app's settings
    # and attach it to app.state so SlowAPIMiddleware can find it.
    configure_from_settings(settings)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # Belt-and-braces: a global unhandled-exception handler that logs the
    # traceback via our app logger. Without this, Starlette's default
    # ServerErrorMiddleware returns a plain "Internal Server Error" body
    # and the traceback goes through uvicorn's error logger — which
    # sometimes renders silently depending on the uvicorn log config.
    # Putting log.exception here guarantees every 500 lands in
    # `docker logs` with the full stack, keyed by request path.
    @app.exception_handler(Exception)
    async def _log_unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

    # Middleware wrapping in Starlette: add_middleware() inserts at the head
    # of user_middleware, and build_middleware_stack iterates via reversed(),
    # so the LAST add_middleware call becomes the OUTERMOST wrapper — first
    # to run on incoming requests. We need:
    #   request → ProxyHeaders → Session → AuthRequired → router
    # so AuthRequired (which reads request.session) sees a populated session
    # scope, and ProxyHeaders (which rewrites scheme from X-Forwarded-Proto)
    # runs before SessionMiddleware checks cookie Secure-flag eligibility.
    # To get that ordering we add in the REVERSE order: innermost first,
    # outermost last.
    app.add_middleware(AuthRequiredMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        # H13: flag drops in dev so http://localhost:8080 keeps the cookie.
        https_only=not settings.dev_mode,
        same_site="lax",
        max_age=14 * 24 * 3600,
    )
    # v0.20.0 — ``trusted_hosts="*"`` let any upstream spoof
    # ``X-Forwarded-Proto`` / ``X-Forwarded-For``. The former can flip
    # the scheme Starlette sees to ``https`` and satisfy the Secure
    # cookie check even on a plaintext request; the latter corrupts
    # rate-limiting and audit-log client IPs. Default to loopback-only
    # (``TRUSTED_PROXIES=127.0.0.1,::1``); deploy topologies behind a
    # proxy on a different host override via env.
    app.add_middleware(
        ProxyHeadersMiddleware,
        trusted_hosts=settings.trusted_proxies_list,
    )

    app.include_router(auth_router.router)
    app.include_router(health_router.router)
    app.include_router(events_router.router)
    app.include_router(logs_router.router)
    app.include_router(instances_router.router)
    app.include_router(schedule_router.router)
    app.include_router(notifications_router.router)
    app.include_router(settings_router.router)
    app.include_router(jobs_router.router)
    app.include_router(backups_router.router)
    app.include_router(audit_router.router)

    spa_dir = static_dir or Path(__file__).resolve().parent / "static"
    mount_spa(app, spa_dir)

    return app
