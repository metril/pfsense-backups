"""``python -m worker backfill-config-versions`` core loop.

Mirrors the reindex CLI test: drives the private
``_backfill_config_versions_core`` helper (the CLI wrapper only adds
settings/engine plumbing) over in-memory SQLite + fake files.

- NULL rows with parseable files get ``config_version`` filled.
- Unreadable files are skipped (stay NULL), counted as skipped.
- Already-filled rows are not re-read (idempotent reruns are cheap).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pfsense_shared.crypto import Crypto
from pfsense_shared.models import Backup, Base, Instance
from worker.__main__ import _backfill_config_versions_core

_XML = b"""<?xml version="1.0"?>
<pfsense>
  <version>22.1</version>
  <system><hostname>gw</hostname><domain>lan</domain></system>
</pfsense>
"""


def test_backfill_fills_skips_and_is_idempotent(tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    crypto = Crypto(Fernet.generate_key())
    log = logging.getLogger("test.backfill")

    with session_factory() as s:
        inst = Instance(
            name="gw-backfill",
            url="https://gw.backfill.test",
            username_ct=crypto.encrypt("a"),
            password_ct=crypto.encrypt("p"),
            backup_prefix="daily",
        )
        s.add(inst)
        s.commit()
        s.refresh(inst)
        iid = inst.id

    t0 = datetime(2026, 6, 1, tzinfo=UTC)

    def seed(when: datetime, *, on_disk: bool, version: str | None = None) -> int:
        p = tmp_path / f"daily_{when.isoformat().replace(':', '-')}.xml"
        if on_disk:
            p.write_bytes(_XML)
        with session_factory() as s:
            row = Backup(
                instance_id=iid,
                started_at=when,
                finished_at=when,
                duration_seconds=1.0,
                filename=p.name,
                path=str(p),
                size_bytes=len(_XML),
                compressed=False,
                success=True,
                encrypted=False,
                config_version=version,
            )
            s.add(row)
            s.commit()
            s.refresh(row)
            return row.id

    fillable = seed(t0, on_disk=True)
    missing_file = seed(t0 + timedelta(days=1), on_disk=False)
    already_set = seed(t0 + timedelta(days=2), on_disk=True, version="21.7")

    filled, skipped = _backfill_config_versions_core(session_factory, crypto, None, log)
    assert (filled, skipped) == (1, 1)

    with session_factory() as s:
        assert s.get(Backup, fillable).config_version == "22.1"
        assert s.get(Backup, missing_file).config_version is None
        # Pre-filled row untouched (targets NULL only).
        assert s.get(Backup, already_set).config_version == "21.7"

    # Rerun: the filled row no longer matches the NULL filter; only the
    # unreadable row is retried (and skipped again).
    filled, skipped = _backfill_config_versions_core(session_factory, crypto, None, log)
    assert (filled, skipped) == (0, 1)
