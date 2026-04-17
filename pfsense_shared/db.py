"""SQLAlchemy engine/session factory with SQLite pragmas + first-run bootstrap."""

from __future__ import annotations

from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import BackupSettings, Base, LoggingSettings


def _sqlite_pragmas(dbapi_conn, _connection_record) -> None:
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


def _singleton_missing(session: Session, model: type[BackupSettings | LoggingSettings]) -> bool:
    return session.execute(select(model).where(model.id == 1)).scalar_one_or_none() is None


def init_db(engine: Engine) -> None:
    """Create tables if missing and seed singleton rows on first run."""
    Base.metadata.create_all(bind=engine)

    session_factory = make_session_factory(engine)
    with session_factory() as session:
        if _singleton_missing(session, BackupSettings):
            session.add(BackupSettings(id=1))
        if _singleton_missing(session, LoggingSettings):
            session.add(LoggingSettings(id=1))
        session.commit()
