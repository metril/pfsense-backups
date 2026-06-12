"""backups.config_version — pfSense config schema version per backup

Revision ID: e1a47f8b2c90
Revises: d9f03e6b4c11
Create Date: 2026-06-12 01:00:00.000000

Stores the ``<version>`` tag from each backup's config.xml (the config
SCHEMA version, e.g. "23.3" — not the pfSense release string, which
isn't in the file). Set by the worker where the post-backup parse
already happens, so it costs nothing extra; NULL means "not parsed
yet" — the ``backfill-config-versions`` CLI subcommand fills history.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1a47f8b2c90"
down_revision: str | None = "d9f03e6b4c11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("backups") as batch_op:
        batch_op.add_column(
            sa.Column("config_version", sa.String(32), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("backups") as batch_op:
        batch_op.drop_column("config_version")
