"""composite index on (instance_id, started_at) for the per-instance history view

Revision ID: d9f03e6b4c11
Revises: c8e92d5a3f10
Create Date: 2026-05-15 12:00:00.000000

The per-instance scrubber at ``/instances/:id/history`` runs
``WHERE instance_id = ? AND success = 1 ORDER BY started_at ASC``
on every page load. With only the single-column ``ix_backups_instance_id``
index, SQLite walks the instance index for the filter then does a
separate post-sort — fine at 100 rows, sluggish at thousands.

Adding a composite ``(instance_id, started_at)`` index lets the
planner satisfy both the WHERE and the ORDER BY by walking a
single covering index range. This is what makes the v0.45.0
"no cap, return all backups" change cheap.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d9f03e6b4c11"
down_revision: str | None = "c8e92d5a3f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("backups") as batch_op:
        batch_op.create_index(
            "ix_backups_instance_started",
            ["instance_id", "started_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("backups") as batch_op:
        batch_op.drop_index("ix_backups_instance_started")
