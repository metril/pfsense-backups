"""Alembic environment.

Picks up the SQLAlchemy URL from the APP_DB_URL env var at runtime rather than
hard-coding it in alembic.ini. Uses render_as_batch so SQLite gets proper
batch-mode ALTERs. APScheduler's `apscheduler_jobs` table is managed by
APScheduler itself (created lazily on first scheduler start), so we exclude
it from autogenerate diffs.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from pfsense_shared.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override alembic.ini's URL with the live env var.
config.set_main_option(
    "sqlalchemy.url",
    os.environ.get("APP_DB_URL", config.get_main_option("sqlalchemy.url", "")),
)

target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to):
    """Filter out tables we don't manage via Alembic."""
    if type_ == "table" and name == "apscheduler_jobs":
        return False
    return True


def run_migrations_offline() -> None:
    """Emit SQL without connecting to a DB (for `alembic upgrade --sql`)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
