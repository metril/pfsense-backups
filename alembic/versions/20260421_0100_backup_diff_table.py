"""precomputed backup diff table

Revision ID: 9c4a3e1b7f2d
Revises: 6b1e4a7d2c9f
Create Date: 2026-04-21 01:00:00.000000

Adds the ``backup_diff`` table — precomputed structural diffs from
each backup against (a) its immediate predecessor and (b) the
oldest-still-on-disk successful backup for the instance. Powers the
v0.37.0 "+N since first" summary badge and the full "diff vs first
backup" view.

Cascade strategy:
  - ``backup_id`` → CASCADE: retention pruning drops diff rows.
  - ``base_backup_id`` → SET NULL: baseline prune leaves the row
    marked stale; read path recomputes + upserts lazily.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9c4a3e1b7f2d"
down_revision: str | None = "6b1e4a7d2c9f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backup_diff",
        sa.Column(
            "backup_id",
            sa.Integer(),
            sa.ForeignKey("backups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column(
            "base_backup_id",
            sa.Integer(),
            sa.ForeignKey("backups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("added_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("removed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("modified_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("full_diff_gz", sa.LargeBinary(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("backup_id", "kind"),
        sa.CheckConstraint(
            "kind IN ('previous', 'first')",
            name="ck_backup_diff_kind",
        ),
    )
    op.create_index(
        "idx_backup_diff_base",
        "backup_diff",
        ["base_backup_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_backup_diff_base", table_name="backup_diff")
    op.drop_table("backup_diff")
