"""instances.stale_after_hours + stale_notified_at — built-in staleness alerts

Revision ID: f2b58a9c3d01
Revises: e1a47f8b2c90
Create Date: 2026-06-12 02:00:00.000000

The worker's periodic staleness check alerts when an enabled, scheduled
instance has no successful backup within its threshold.
``stale_after_hours`` NULL = auto-derived from the cron cadence;
``stale_notified_at`` is the alert-suppression stamp (re-alert after
24h, cleared by the next successful backup).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2b58a9c3d01"
down_revision: str | None = "e1a47f8b2c90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("instances") as batch_op:
        batch_op.add_column(
            sa.Column("stale_after_hours", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("stale_notified_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("instances") as batch_op:
        batch_op.drop_column("stale_notified_at")
        batch_op.drop_column("stale_after_hours")
