"""notification kinds + per-instance scope + healthchecks auto-flip

Revision ID: 9d4f1c6a8e3b
Revises: 8a1c3e9d5b2f
Create Date: 2026-04-18 23:45:00.000000

Adds ``notifications.kind`` (first-class channel discriminator),
``notifications.config_json`` (kind-specific structured config), and
``notifications.instance_ids_json`` (per-instance scope filter). Also
auto-flips existing rows whose URL matches a Healthchecks ping endpoint
from ``kind='webhook'`` to ``kind='healthchecks'`` so behavior continues
unchanged for users who configured Healthchecks via the legacy URL sniff.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9d4f1c6a8e3b"
down_revision: str | None = "8a1c3e9d5b2f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "kind",
                sa.String(length=32),
                nullable=False,
                server_default="webhook",
            )
        )
        batch_op.add_column(
            sa.Column("config_json", sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("instance_ids_json", sa.Text(), nullable=True)
        )

    # Flip legacy Healthchecks webhooks to the first-class kind so the
    # new dispatcher's /fail path is used. Covers hosted (hc-ping.com),
    # self-hosted URLs whose hostname includes "healthchecks", and the
    # canonical self-hosted path `{base}/ping/{uuid-or-slug}`.
    op.execute(
        "UPDATE notifications "
        "SET kind = 'healthchecks' "
        "WHERE kind = 'webhook' "
        "AND (url LIKE '%hc-ping.com%' "
        "     OR url LIKE '%healthchecks%' "
        "     OR url LIKE '%/ping/%')"
    )


def downgrade() -> None:
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.drop_column("instance_ids_json")
        batch_op.drop_column("config_json")
        batch_op.drop_column("kind")
