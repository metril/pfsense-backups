"""instances GFS retention tier columns

Revision ID: a3c69b0d4e12
Revises: f2b58a9c3d01
Create Date: 2026-06-12 03:00:00.000000

Four nullable tier knobs (keep-all days, daily days, weekly weeks,
monthly months). All NULL preserves the existing count-only retention
exactly, so upgrades change nothing until an operator opts in.
``retention_count`` remains as a max cap applied after tier selection.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3c69b0d4e12"
down_revision: str | None = "f2b58a9c3d01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    "retention_keep_all_days",
    "retention_daily_days",
    "retention_weekly_weeks",
    "retention_monthly_months",
)


def upgrade() -> None:
    with op.batch_alter_table("instances") as batch_op:
        for name in _COLUMNS:
            batch_op.add_column(sa.Column(name, sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("instances") as batch_op:
        for name in reversed(_COLUMNS):
            batch_op.drop_column(name)
