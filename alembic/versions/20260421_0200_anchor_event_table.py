"""anchor_event table + Instance.anchor_events_backfilled_at

Revision ID: a1e23f4b6d81
Revises: 9c4a3e1b7f2d
Create Date: 2026-04-21 02:00:00.000000

Adds the ``anchor_event`` table — per-anchor change log populated at
backup ingestion. Powers the v0.40.0 blame-drawer rewrite, the
inline blame tooltip, and the cumulative-changes page.

Also adds ``Instance.anchor_events_backfilled_at`` so read endpoints
can distinguish "indexed — serve from table" from "pre-v0.40.0
instance — fall back to legacy full-history walk."

Cascade strategy:
  - ``instance_id`` → CASCADE: deleting an instance drops its events.
  - ``backup_id`` → CASCADE: retention prune of a backup drops its
    events. Matches existing blame semantics (history only covers
    retained backups).
  - ``prev_backup_id`` → SET NULL: predecessor prune leaves the
    event intact with a NULL pointer — the row's existence is what
    the index cares about.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1e23f4b6d81"
down_revision: str | None = "9c4a3e1b7f2d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "instances",
        sa.Column(
            "anchor_events_backfilled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_table(
        "anchor_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "instance_id",
            sa.Integer(),
            sa.ForeignKey("instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "backup_id",
            sa.Integer(),
            sa.ForeignKey("backups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "prev_backup_id",
            sa.Integer(),
            sa.ForeignKey("backups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("anchor_id", sa.String(length=255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "kind in ('added','modified','removed','reordered')",
            name="ck_anchor_event_kind",
        ),
    )
    op.create_index(
        "ix_anchor_event_lookup",
        "anchor_event",
        ["instance_id", "anchor_id", "occurred_at"],
    )
    op.create_index(
        "ix_anchor_event_backup",
        "anchor_event",
        ["backup_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_anchor_event_backup", table_name="anchor_event")
    op.drop_index("ix_anchor_event_lookup", table_name="anchor_event")
    op.drop_table("anchor_event")
    op.drop_column("instances", "anchor_events_backfilled_at")
