"""Engine/session factories + Alembic-driven first-run bootstrap.

init_db() is the single entry point both services call on boot. It takes
out an exclusive file lock on ``<data_dir>/.init.lock`` (M7) so two
containers starting simultaneously don't race on ``alembic upgrade head``
or the singleton seeding that follows.
"""

from __future__ import annotations

import contextlib
import fcntl
import logging
import os
from collections.abc import Iterator
from pathlib import Path

from alembic.config import Config as AlembicConfig
from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

from alembic import command

from .models import BackupSettings, LoggingSettings

log = logging.getLogger(__name__)


# --------------------------------------------------------------------- #
# Sync engine (worker + one-shot migrations)
# --------------------------------------------------------------------- #


def _sqlite_pragmas(
    dbapi_conn: DBAPIConnection,
    _connection_record: ConnectionPoolEntry,
) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def make_engine(url: str) -> Engine:
    from sqlalchemy import create_engine

    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)

    if url.startswith("sqlite"):
        event.listen(engine, "connect", _sqlite_pragmas)

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


# --------------------------------------------------------------------- #
# Async engine (web service)
# --------------------------------------------------------------------- #


def _async_url(url: str) -> str:
    """Translate a sync SQLite URL into its aiosqlite equivalent.

    Leaves non-sqlite URLs untouched for future-proofing (postgres+asyncpg,
    mysql+aiomysql, etc. can be adopted by prepending the right driver).
    """
    if url.startswith("sqlite:///") and "+aiosqlite" not in url:
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


def make_async_engine(
    url: str,
    *,
    pool_size: int = 20,
    max_overflow: int = 40,
) -> AsyncEngine:
    # Defaults bumped from SQLAlchemy's 5/10 because endpoints that parse
    # a config inside ``asyncio.to_thread`` (notably ``/parsed`` and
    # ``/instance/{id}/anchor-history``) hold a pool connection while the
    # parse runs. Under modest concurrency the old 15-slot ceiling hit
    # QueuePool TimeoutError. SQLite + aiosqlite is happy with many
    # connections — WAL allows parallel readers, writes still serialise
    # via ``busy_timeout``.
    async_url = _async_url(url)
    connect_args = {}
    if async_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_async_engine(
        async_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
    )

    # WAL + foreign_keys + busy_timeout on every connection. The sync event
    # listener receives DBAPI connections synchronously even for the async
    # engine (aiosqlite wraps sqlite3 in a thread), so the same hook works.
    if async_url.startswith("sqlite"):
        # aiosqlite's sync callback signature passes the raw sqlite3.Connection,
        # so the same _sqlite_pragmas body applies.
        event.listen(engine.sync_engine, "connect", _sqlite_pragmas)

    return engine


def make_async_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )


# --------------------------------------------------------------------- #
# Migrations + seed
# --------------------------------------------------------------------- #


def _alembic_config(db_url: str) -> AlembicConfig:
    """Build an Alembic Config pointing at our repo-level alembic.ini.

    When called from inside a container this resolves to /app/alembic.ini
    (both Dockerfiles COPY it); locally it resolves to the repo root.
    """
    ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    cfg = AlembicConfig(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", db_url)
    # script_location is relative to alembic.ini; reassert absolute so the
    # config keeps working even if someone runs us from a weird CWD.
    cfg.set_main_option("script_location", str(ini_path.parent / "alembic"))
    return cfg


def _lock_path(db_url: str) -> Path:
    """Derive an init-lock path from the DB URL.

    For sqlite URLs the lock sits next to the DB file. For anything else
    (not currently in use, but future-proof) we fall back to /tmp.
    """
    if db_url.startswith("sqlite:///"):
        db_file = Path(db_url.removeprefix("sqlite:///"))
        return db_file.parent / ".init.lock"
    return Path("/tmp/pfsense-backups-init.lock")


@contextlib.contextmanager
def _exclusive_file_lock(path: Path) -> Iterator[None]:
    """Block until an exclusive flock on ``path`` is acquired."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Using an os.open handle avoids pyflakes warnings about the variable
    # being unused; we hold the fd for the lifetime of the with-block.
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def run_migrations(db_url: str) -> None:
    """Run ``alembic upgrade head`` in-process using our repo's config."""
    cfg = _alembic_config(db_url)
    log.info("Running Alembic migrations → head")
    command.upgrade(cfg, "head")


def _singleton_missing(session: Session, model: type[BackupSettings | LoggingSettings]) -> bool:
    return session.execute(select(model).where(model.id == 1)).scalar_one_or_none() is None


def seed_singletons(session_factory: sessionmaker[Session]) -> None:
    """Idempotent seed of BackupSettings + LoggingSettings singleton rows."""
    with session_factory() as session:
        if _singleton_missing(session, BackupSettings):
            session.add(BackupSettings(id=1))
        if _singleton_missing(session, LoggingSettings):
            session.add(LoggingSettings(id=1))
        session.commit()


def init_db(engine: Engine) -> None:
    """Apply migrations + seed singletons under a file lock.

    Signature kept compatible with the old `create_all`-based init so
    `worker/__main__.py` doesn't need to change call shape.
    """
    url = str(engine.url)
    with _exclusive_file_lock(_lock_path(url)):
        run_migrations(url)
        seed_singletons(make_session_factory(engine))
