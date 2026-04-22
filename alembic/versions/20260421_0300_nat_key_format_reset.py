"""reset anchor_event index on NAT key format change

Revision ID: b7d91c4f2a05
Revises: a1e23f4b6d81
Create Date: 2026-04-21 03:00:00.000000

v0.40.1 changed the NAT rule key derivation in
``pfsense_shared/pfsense_sections/nat.py:_key`` — dropped ``<descr>``
and added full source/destination endpoint tuples. The old
``hash:<digest>`` keys persisted in ``anchor_event.anchor_id`` no
longer match what a fresh parse of the same backup would produce, so
every NAT anchor's indexed blame would show an empty timeline.

This migration:

1. Truncates ``anchor_event`` (cheap — nothing we can't rebuild by
   replaying the chain of retained backups).
2. Nulls ``Instance.anchor_events_backfilled_at`` on every row so
   read endpoints fall back to the legacy walk-and-parse path for
   blame / history / cumulative-changes until reindexed.

Operator action: run ``python -m worker reindex-anchor-events`` on
the worker once the new code is live. The legacy path remains
functional in the interim — users see blame, just via the slower
query. On reindex completion, the flag is re-stamped and the fast
path kicks back in.

Non-destructive in a meaningful sense: the ``Backup`` rows and the
encrypted XML blobs on disk are untouched; the event log gets
rebuilt from them deterministically.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b7d91c4f2a05"
down_revision: str | None = "a1e23f4b6d81"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Wipe the event log and the backfill flag so the read path
    # falls back to the legacy scan-and-parse until a reindex lands.
    op.execute("DELETE FROM anchor_event")
    op.execute("UPDATE instances SET anchor_events_backfilled_at = NULL")


def downgrade() -> None:
    # No-op: the index is rebuildable data; there's nothing to
    # restore on downgrade, and re-stamping the backfill flag would
    # lie about indexed-ness.
    pass
