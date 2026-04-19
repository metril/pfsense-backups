"""backup_all_max_workers on backup_settings

Revision ID: 2f5a9c8e1d3b
Revises: 9d4f1c6a8e3b
Create Date: 2026-04-19 01:00:00.000000

Adds a configurable cap on the number of instances ``backup_all`` backs
up concurrently. Default of 4 preserves prior behavior (previously a
class constant in ``worker/backup_manager.py``) while letting operators
tune up (more parallel pfSense logins) or down (gentler on a shared
host) from the Settings page without restarting the worker.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "2f5a9c8e1d3b"
down_revision: str | None = "9d4f1c6a8e3b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("backup_settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "backup_all_max_workers",
                sa.Integer(),
                nullable=False,
                server_default="4",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("backup_settings", schema=None) as batch_op:
        batch_op.drop_column("backup_all_max_workers")
