"""off-site replication: settings singleton + Backup state + Instance flag

Revision ID: c5e81d2f6a34
Revises: b4d70c1e5f23
Create Date: 2026-06-12 05:00:00.000000

One migration for the whole F3 surface: the ``replication_settings``
singleton (one global destination, credentials as Fernet ciphertext),
per-backup replica lifecycle columns (status/key/at/error/attempts/
sha256 + ``local_present`` for off-site-only rows), and the per-instance
``replicate`` opt-in flag.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c5e81d2f6a34"
down_revision: str | None = "b4d70c1e5f23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "replication_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("kind", sa.String(16), nullable=False, server_default="s3"),
        sa.Column("s3_endpoint_url", sa.String(512), nullable=True),
        sa.Column("s3_region", sa.String(64), nullable=True),
        sa.Column("s3_bucket", sa.String(255), nullable=True),
        sa.Column("s3_access_key_id", sa.String(255), nullable=True),
        sa.Column("s3_secret_access_key_ct", sa.LargeBinary(), nullable=True),
        sa.Column("sftp_host", sa.String(255), nullable=True),
        sa.Column("sftp_port", sa.Integer(), nullable=False, server_default="22"),
        sa.Column("sftp_username", sa.String(128), nullable=True),
        sa.Column("sftp_password_ct", sa.LargeBinary(), nullable=True),
        sa.Column("sftp_private_key_ct", sa.LargeBinary(), nullable=True),
        sa.Column(
            "base_path", sa.String(512), nullable=False,
            server_default="pfsense-backups",
        ),
        sa.Column(
            "encrypt_plaintext", sa.Boolean(), nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "double_encrypt", sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("replication_password_ct", sa.LargeBinary(), nullable=True),
        sa.Column(
            "mirror_deletes", sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
    )

    with op.batch_alter_table("backups") as batch_op:
        batch_op.add_column(sa.Column("replica_status", sa.String(16), nullable=True))
        batch_op.add_column(sa.Column("replica_key", sa.String(1024), nullable=True))
        batch_op.add_column(
            sa.Column("replica_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("replica_error", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "replica_attempts", sa.Integer(), nullable=False, server_default="0"
            )
        )
        batch_op.add_column(sa.Column("replica_sha256", sa.String(64), nullable=True))
        batch_op.add_column(
            sa.Column(
                "local_present", sa.Boolean(), nullable=False,
                server_default=sa.true(),
            )
        )

    with op.batch_alter_table("instances") as batch_op:
        batch_op.add_column(
            sa.Column(
                "replicate", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("instances") as batch_op:
        batch_op.drop_column("replicate")
    with op.batch_alter_table("backups") as batch_op:
        for name in (
            "local_present",
            "replica_sha256",
            "replica_attempts",
            "replica_error",
            "replica_at",
            "replica_key",
            "replica_status",
        ):
            batch_op.drop_column(name)
    op.drop_table("replication_settings")
