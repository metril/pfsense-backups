"""F2: ``_cleanup_old_backups`` with GFS tiers — rows + files on disk,
assert the keep-set complement is unlinked and deleted.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pfsense_shared.crypto import Crypto
from pfsense_shared.models import Backup, Base, Instance
from worker.backup_manager import PfSenseBackupManager, _InstanceSnapshot

NOW = datetime.now(UTC)


def _snapshot(instance_id: int, **retention) -> _InstanceSnapshot:
    return _InstanceSnapshot(
        id=instance_id,
        name="gw-gfs",
        url="https://gw.gfs.test",
        username="a",
        password="p",
        subfolder=None,
        backup_prefix="daily",
        verify_ssl=False,
        timeout=30,
        retention_count=retention.get("retention_count", 365),
        compress=False,
        replicate=False,
        retention_keep_all_days=retention.get("keep_all_days"),
        retention_daily_days=retention.get("daily_days"),
        retention_weekly_weeks=retention.get("weekly_weeks"),
        retention_monthly_months=retention.get("monthly_months"),
        directory="/backups",
        filename_format="{prefix}_{instance_name}_{timestamp}.xml",
        timestamp_format="%Y-%m-%d",
        backup_area="",
        backup_include_rrd=False,
        backup_include_packages=True,
        backup_include_ssh=True,
        backup_encrypt=False,
        backup_encrypt_password=None,
    )


def test_gfs_cleanup_unlinks_complement(tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    crypto = Crypto(Fernet.generate_key())

    with session_factory() as s:
        inst = Instance(
            name="gw-gfs",
            url="https://gw.gfs.test",
            username_ct=crypto.encrypt("a"),
            password_ct=crypto.encrypt("p"),
            backup_prefix="daily",
        )
        s.add(inst)
        s.commit()
        s.refresh(inst)
        iid = inst.id

    # 30 daily backups, two per day would be richer but daily suffices:
    # keep-all 2 days + daily tier 7 days + cap 100.
    paths: dict[int, Path] = {}
    with session_factory() as s:
        for i in range(30):
            when = NOW - timedelta(days=i, hours=1)
            p = tmp_path / f"b{i}.xml"
            p.write_bytes(b"<pfsense/>")
            row = Backup(
                instance_id=iid,
                started_at=when,
                finished_at=when,
                duration_seconds=1.0,
                filename=p.name,
                path=str(p),
                size_bytes=10,
                compressed=False,
                success=True,
                encrypted=False,
            )
            s.add(row)
            s.flush()
            paths[row.id] = p
        s.commit()

    manager = PfSenseBackupManager(
        session_factory=session_factory,
        publisher=MagicMock(),
        metrics=MagicMock(),
        crypto=crypto,
        notifier=MagicMock(),
        hostname="t",
        instance_locks=MagicMock(),
        cross_process_lock=MagicMock(),
    )
    removed = manager._cleanup_old_backups(
        _snapshot(iid, keep_all_days=2, daily_days=7)
    )

    with session_factory() as s:
        remaining = set(
            s.execute(select(Backup.id).where(Backup.instance_id == iid))
            .scalars()
            .all()
        )
    # 30 dailies: keep-all window covers ~2-3, daily tier covers one per
    # day for 7 days (overlapping); everything older is pruned.
    assert removed == 30 - len(remaining)
    assert 7 <= len(remaining) <= 9
    # Files agree with rows.
    for bid, p in paths.items():
        assert p.exists() == (bid in remaining)


def test_count_only_cleanup_unchanged(tmp_path: Path) -> None:
    """No tiers → legacy newest-N behavior, exactly."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    crypto = Crypto(Fernet.generate_key())
    with session_factory() as s:
        inst = Instance(
            name="gw-gfs",
            url="https://gw.gfs.test",
            username_ct=crypto.encrypt("a"),
            password_ct=crypto.encrypt("p"),
            backup_prefix="daily",
        )
        s.add(inst)
        s.commit()
        s.refresh(inst)
        iid = inst.id
        for i in range(10):
            when = NOW - timedelta(days=i)
            p = tmp_path / f"c{i}.xml"
            p.write_bytes(b"<pfsense/>")
            s.add(
                Backup(
                    instance_id=iid,
                    started_at=when,
                    finished_at=when,
                    duration_seconds=1.0,
                    filename=p.name,
                    path=str(p),
                    size_bytes=10,
                    compressed=False,
                    success=True,
                    encrypted=False,
                )
            )
        s.commit()

    manager = PfSenseBackupManager(
        session_factory=session_factory,
        publisher=MagicMock(),
        metrics=MagicMock(),
        crypto=crypto,
        notifier=MagicMock(),
        hostname="t",
        instance_locks=MagicMock(),
        cross_process_lock=MagicMock(),
    )
    removed = manager._cleanup_old_backups(_snapshot(iid, retention_count=3))
    assert removed == 7
    with session_factory() as s:
        rows = (
            s.execute(
                select(Backup)
                .where(Backup.instance_id == iid)
                .order_by(Backup.started_at.desc())
            )
            .scalars()
            .all()
        )
    assert len(rows) == 3
