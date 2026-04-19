"""promote timezone to global setting with per-instance override

Revision ID: 8a1c3e9d5b2f
Revises: 7c2a9f6d1e4b
Create Date: 2026-04-18 23:30:00.000000

Adds ``backup_settings.default_timezone`` (the primary control) and
relaxes ``instances.cron_timezone`` to NULLABLE so null means "inherit
global". Existing instances keep whatever string they had — the
effective tz matches prior behavior until a user explicitly clears
the per-instance override.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8a1c3e9d5b2f"
down_revision: str | None = "7c2a9f6d1e4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("backup_settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "default_timezone",
                sa.String(length=64),
                nullable=False,
                server_default="UTC",
            )
        )

    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.alter_column(
            "cron_timezone",
            existing_type=sa.String(length=64),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("instances", schema=None) as batch_op:
        # Downgrade has no way to backfill nulls — UTC is the safest choice
        # since that was the pre-migration default.
        batch_op.alter_column(
            "cron_timezone",
            existing_type=sa.String(length=64),
            nullable=False,
            server_default="UTC",
        )

    with op.batch_alter_table("backup_settings", schema=None) as batch_op:
        batch_op.drop_column("default_timezone")
