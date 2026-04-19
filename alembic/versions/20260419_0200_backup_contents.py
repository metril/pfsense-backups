"""configurable backup contents + per-backup tracking

Revision ID: 6b1e4a7d2c9f
Revises: 2f5a9c8e1d3b
Create Date: 2026-04-19 02:00:00.000000

Adds per-instance controls for what to pull from pfSense's
diag_backup.php (``backup_area``, RRD/packages/SSH toggles, encryption
+ Fernet-encrypted password), plus per-backup columns that mirror what
was actually captured on each row. Server defaults match today's
hard-coded behavior so upgrades don't change what's backed up.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "6b1e4a7d2c9f"
down_revision: str | None = "2f5a9c8e1d3b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "backup_area",
                sa.String(length=64),
                nullable=False,
                server_default="",
            )
        )
        batch_op.add_column(
            sa.Column(
                "backup_include_rrd",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "backup_include_packages",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "backup_include_ssh",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "backup_encrypt",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column("backup_encrypt_password_ct", sa.LargeBinary(), nullable=True)
        )

    with op.batch_alter_table("backups", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "area",
                sa.String(length=64),
                nullable=False,
                server_default="",
            )
        )
        batch_op.add_column(
            sa.Column(
                "included_rrd",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "included_packages",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "included_ssh",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "encrypted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column("encrypt_password_ct", sa.LargeBinary(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("backups", schema=None) as batch_op:
        batch_op.drop_column("encrypt_password_ct")
        batch_op.drop_column("encrypted")
        batch_op.drop_column("included_ssh")
        batch_op.drop_column("included_packages")
        batch_op.drop_column("included_rrd")
        batch_op.drop_column("area")

    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.drop_column("backup_encrypt_password_ct")
        batch_op.drop_column("backup_encrypt")
        batch_op.drop_column("backup_include_ssh")
        batch_op.drop_column("backup_include_packages")
        batch_op.drop_column("backup_include_rrd")
        batch_op.drop_column("backup_area")
