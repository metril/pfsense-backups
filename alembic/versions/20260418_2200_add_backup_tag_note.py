"""add tag + note columns to backups

Revision ID: 7c2a9f6d1e4b
Revises: 0505c45d3d89
Create Date: 2026-04-18 22:00:00.000000

Adds two optional columns so users can pin/label a particular backup
(``tag``, short free-form label) and attach free-text context
(``note``). Both are nullable — existing rows are unaffected.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7c2a9f6d1e4b"
down_revision: str | None = "0505c45d3d89"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("backups", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tag", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("note", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("backups", schema=None) as batch_op:
        batch_op.drop_column("note")
        batch_op.drop_column("tag")
