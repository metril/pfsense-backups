"""reset anchor_event index on filter (firewall) key format change

Revision ID: c8e92d5a3f10
Revises: b7d91c4f2a05
Create Date: 2026-04-22 01:00:00.000000

v0.41.0 ported the v0.40.1 NAT content-hash pattern to
``pfsense_shared/pfsense_sections/firewall.py:_rule_key``. The
pre-tracker fallback used to hash ``(descr, type, interface,
protocol)``; editing the description would fork blame into a
remove+add pair. The new fallback hashes functional fields
(interface, ipprotocol, protocol, source/destination endpoint
blobs, gateway, disabled) with ``<descr>`` deliberately excluded.

Modern configs with ``<tracker>`` are unaffected (the primary path
never changed). Only the minority of rules falling through to the
hash key see a shape change — but we can't tell which those are
per-instance, so the safe move is to reset the index for every
instance the same way the v0.40.1 NAT migration did.

Operator action: run ``python -m worker reindex-anchor-events`` on
the worker once the new code is live. Until then, the read path
falls back to the legacy scan-and-parse route.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "c8e92d5a3f10"
down_revision: str | None = "b7d91c4f2a05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM anchor_event")
    op.execute("UPDATE instances SET anchor_events_backfilled_at = NULL")


def downgrade() -> None:
    # No-op: same reasoning as the NAT reset migration; the index is
    # rebuildable from retained backups, so there's nothing to
    # restore on downgrade.
    pass
