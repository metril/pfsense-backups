"""F3 off-site replication, driven through a recording FakeTarget:

- plaintext source → uploaded blob is pfSense-encrypted and round-trips
  with the replication password;
- gzipped plaintext is gunzipped before encryption;
- already-encrypted source uploads byte-identical (single layer) or,
  with ``double_encrypt``, gains a strippable outer layer (``.2x`` key);
- refusal when encryption is on without a password;
- failure → status/attempts/backoff; upload-verify mismatch ≠ done;
- ``verify_replicas`` flags missing/corrupt remotes back to failed;
- retention keeps replicated rows as off-site-only (AnchorEvents
  survive) and ``retrieve_replica`` restores the original bytes.
"""

from __future__ import annotations

import gzip
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pfsense_shared.crypto import Crypto
from pfsense_shared.models import (
    AnchorEvent,
    Backup,
    Base,
    Instance,
    ReplicationSettings,
)
from pfsense_shared.pfsense_crypto import (
    decrypt_pfsense_backup,
    encrypt_pfsense_backup,
    looks_encrypted,
)
from worker.backup_manager import PfSenseBackupManager, _InstanceSnapshot
from worker.replication import (
    ReplicationConfig,
    load_config,
    replicate_backup,
    retrieve_replica,
    sweep_pending,
    verify_replicas,
)

XML = b'<?xml version="1.0"?>\n<pfsense><version>23.3</version></pfsense>\n'
INSTANCE_PW = "instance-pass-XYZ"
REPL_PW = "replication-pass-ABC"


class FakeTarget:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_uploads = False
        self.truncate_verify = False

    def upload(self, key: str, data: bytes) -> None:
        if self.fail_uploads:
            raise RuntimeError("simulated upload failure")
        self.objects[key] = data

    def head_size(self, key: str) -> int | None:
        if key not in self.objects:
            return None
        size = len(self.objects[key])
        return size - 1 if self.truncate_verify else size

    def download(self, key: str) -> bytes:
        return self.objects[key]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def ping(self) -> None:
        pass


def _setup(tmp_path: Path, **settings_overrides):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    crypto = Crypto(Fernet.generate_key())
    with session_factory() as s:
        inst = Instance(
            name="gw-repl",
            url="https://gw.repl.test",
            username_ct=crypto.encrypt("a"),
            password_ct=crypto.encrypt("p"),
            backup_prefix="daily",
            replicate=True,
        )
        s.add(inst)
        defaults: dict = dict(
            id=1,
            enabled=True,
            kind="s3",
            s3_bucket="bkt",
            base_path="pfsense-backups",
            encrypt_plaintext=True,
            double_encrypt=False,
            replication_password_ct=crypto.encrypt(REPL_PW),
            mirror_deletes=False,
        )
        defaults.update(settings_overrides)
        s.add(ReplicationSettings(**defaults))
        s.commit()
        s.refresh(inst)
    return session_factory, crypto, inst.id


def _seed_backup(
    session_factory, tmp_path: Path, iid: int, *,
    content: bytes = XML, encrypted: bool = False, compressed: bool = False,
    when: datetime | None = None, name: str = "daily_gw_2026-06-01.xml",
) -> int:
    p = tmp_path / name
    p.write_bytes(content)
    when = when or datetime(2026, 6, 1, tzinfo=UTC)
    with session_factory() as s:
        row = Backup(
            instance_id=iid, started_at=when, finished_at=when,
            duration_seconds=1.0, filename=p.name, path=str(p),
            size_bytes=len(content), compressed=compressed, success=True,
            encrypted=encrypted, replica_status="pending",
        )
        if encrypted:
            crypto_pw_ct = None  # not needed by replication
            row.encrypt_password_ct = crypto_pw_ct
        s.add(row)
        s.commit()
        s.refresh(row)
        return row.id


def _row(session_factory, bid: int) -> Backup:
    with session_factory() as s:
        return s.get(Backup, bid)


def test_plaintext_uploads_encrypted_and_round_trips(tmp_path: Path) -> None:
    session_factory, crypto, iid = _setup(tmp_path)
    bid = _seed_backup(session_factory, tmp_path, iid)
    target = FakeTarget()

    assert replicate_backup(session_factory, crypto, bid, target=target)

    row = _row(session_factory, bid)
    assert row.replica_status == "done"
    assert row.replica_key.endswith(".xml.enc")
    assert row.replica_sha256
    blob = target.objects[row.replica_key]
    assert looks_encrypted(blob)
    assert decrypt_pfsense_backup(blob, REPL_PW) == XML


def test_gzipped_plaintext_is_unwrapped_first(tmp_path: Path) -> None:
    session_factory, crypto, iid = _setup(tmp_path)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write(XML)
    bid = _seed_backup(
        session_factory, tmp_path, iid, content=buf.getvalue(),
        compressed=True, name="daily_gw.xml.gz",
    )
    target = FakeTarget()
    assert replicate_backup(session_factory, crypto, bid, target=target)
    row = _row(session_factory, bid)
    assert decrypt_pfsense_backup(target.objects[row.replica_key], REPL_PW) == XML


def test_encrypted_source_uploads_as_is(tmp_path: Path) -> None:
    session_factory, crypto, iid = _setup(tmp_path)
    enc = encrypt_pfsense_backup(XML, INSTANCE_PW)
    bid = _seed_backup(session_factory, tmp_path, iid, content=enc, encrypted=True)
    target = FakeTarget()
    assert replicate_backup(session_factory, crypto, bid, target=target)
    row = _row(session_factory, bid)
    assert row.replica_key.endswith(".xml.enc")
    assert not row.replica_key.endswith(".2x.xml.enc")
    assert target.objects[row.replica_key] == enc  # byte-identical


def test_double_encrypt_round_trips_both_layers(tmp_path: Path) -> None:
    session_factory, crypto, iid = _setup(tmp_path, double_encrypt=True)
    enc = encrypt_pfsense_backup(XML, INSTANCE_PW)
    bid = _seed_backup(session_factory, tmp_path, iid, content=enc, encrypted=True)
    target = FakeTarget()
    assert replicate_backup(session_factory, crypto, bid, target=target)
    row = _row(session_factory, bid)
    assert row.replica_key.endswith(".2x.xml.enc")
    blob = target.objects[row.replica_key]
    inner = decrypt_pfsense_backup(blob, REPL_PW)  # outer: replication pw
    assert inner == enc
    assert decrypt_pfsense_backup(inner, INSTANCE_PW) == XML  # inner: instance pw


def test_refusal_without_password(tmp_path: Path) -> None:
    session_factory, crypto, iid = _setup(tmp_path, replication_password_ct=None)
    bid = _seed_backup(session_factory, tmp_path, iid)
    target = FakeTarget()
    assert not replicate_backup(session_factory, crypto, bid, target=target)
    row = _row(session_factory, bid)
    assert row.replica_status == "failed"
    assert "password" in row.replica_error
    assert target.objects == {}


def test_upload_verify_mismatch_is_not_done(tmp_path: Path) -> None:
    session_factory, crypto, iid = _setup(tmp_path)
    bid = _seed_backup(session_factory, tmp_path, iid)
    target = FakeTarget()
    target.truncate_verify = True
    assert not replicate_backup(session_factory, crypto, bid, target=target)
    row = _row(session_factory, bid)
    assert row.replica_status == "failed"
    assert "verify" in row.replica_error


def test_failure_increments_attempts_and_sweep_backs_off(tmp_path: Path) -> None:
    session_factory, crypto, iid = _setup(tmp_path)
    bid = _seed_backup(session_factory, tmp_path, iid)
    target = FakeTarget()
    target.fail_uploads = True

    assert not replicate_backup(session_factory, crypto, bid, target=target)
    assert _row(session_factory, bid).replica_attempts == 1

    # Sweep immediately after: backoff (10 min) not yet elapsed → skip.
    now = datetime.now(UTC)
    assert sweep_pending(session_factory, crypto, now=now, target=target) == 0
    assert _row(session_factory, bid).replica_attempts == 1

    # Past the backoff window the sweep retries (and succeeds).
    target.fail_uploads = False
    later = now + timedelta(minutes=11)
    assert sweep_pending(session_factory, crypto, now=later, target=target) == 1
    assert _row(session_factory, bid).replica_status == "done"


def test_verify_replicas_flags_missing_and_corrupt(tmp_path: Path) -> None:
    session_factory, crypto, iid = _setup(tmp_path)
    b1 = _seed_backup(session_factory, tmp_path, iid, name="b1.xml")
    b2 = _seed_backup(session_factory, tmp_path, iid, name="b2.xml")
    target = FakeTarget()
    assert replicate_backup(session_factory, crypto, b1, target=target)
    assert replicate_backup(session_factory, crypto, b2, target=target)

    # b1's remote object vanishes; b2's gets corrupted.
    target.objects.pop(_row(session_factory, b1).replica_key)
    target.objects[_row(session_factory, b2).replica_key] = b"garbage-same-len-no"

    checked, flagged = verify_replicas(session_factory, crypto, deep=True, target=target)
    assert checked == 2
    assert flagged == 2
    assert _row(session_factory, b1).replica_status == "failed"
    assert "missing" in _row(session_factory, b1).replica_error
    assert _row(session_factory, b2).replica_status == "failed"


def _manager(session_factory, crypto) -> PfSenseBackupManager:
    return PfSenseBackupManager(
        session_factory=session_factory,
        publisher=MagicMock(),
        metrics=MagicMock(),
        crypto=crypto,
        notifier=MagicMock(),
        hostname="t",
        instance_locks=MagicMock(),
        cross_process_lock=MagicMock(),
    )


def _snapshot(iid: int, retention_count: int) -> _InstanceSnapshot:
    return _InstanceSnapshot(
        id=iid, name="gw-repl", url="https://gw.repl.test", username="a",
        password="p", subfolder=None, backup_prefix="daily", verify_ssl=False,
        timeout=30, retention_count=retention_count, compress=False,
        replicate=True, retention_keep_all_days=None, retention_daily_days=None,
        retention_weekly_weeks=None, retention_monthly_months=None,
        directory="/backups", filename_format="{prefix}.xml",
        timestamp_format="%Y-%m-%d", backup_area="", backup_include_rrd=False,
        backup_include_packages=True, backup_include_ssh=True,
        backup_encrypt=False, backup_encrypt_password=None,
    )


def test_retention_keeps_replicated_rows_as_offsite_only(tmp_path: Path) -> None:
    session_factory, crypto, iid = _setup(tmp_path)
    t0 = datetime(2026, 6, 1, tzinfo=UTC)
    old = _seed_backup(
        session_factory, tmp_path, iid, when=t0, name="old.xml"
    )
    _seed_backup(
        session_factory, tmp_path, iid, when=t0 + timedelta(days=1), name="new.xml"
    )
    # Give the old row a verified replica + an anchor event.
    target = FakeTarget()
    assert replicate_backup(session_factory, crypto, old, target=target)
    with session_factory() as s:
        s.add(
            AnchorEvent(
                instance_id=iid, backup_id=old, prev_backup_id=None,
                anchor_id="field-system-hostname", occurred_at=t0,
                kind="added", value_json='"gw"',
            )
        )
        s.commit()

    removed = _manager(session_factory, crypto)._cleanup_old_backups(
        _snapshot(iid, retention_count=1)
    )

    # Old row survives as off-site only (not counted as removed).
    assert removed == 0
    row = _row(session_factory, old)
    assert row is not None
    assert row.local_present is False
    assert not (tmp_path / "old.xml").exists()
    assert (tmp_path / "new.xml").exists()
    with session_factory() as s:
        events = s.execute(
            select(AnchorEvent).where(AnchorEvent.backup_id == old)
        ).scalars().all()
    assert len(events) == 1  # CASCADE didn't fire — history survives


def test_retrieve_replica_restores_original_bytes(tmp_path: Path) -> None:
    session_factory, crypto, iid = _setup(tmp_path)
    bid = _seed_backup(session_factory, tmp_path, iid)
    target = FakeTarget()
    assert replicate_backup(session_factory, crypto, bid, target=target)

    # Simulate retention: local file gone, row off-site only.
    path = Path(_row(session_factory, bid).path)
    path.unlink()
    with session_factory() as s:
        row = s.get(Backup, bid)
        row.local_present = False
        s.commit()

    retrieve_replica(session_factory, crypto, bid, target=target)

    row = _row(session_factory, bid)
    assert row.local_present is True
    assert path.read_bytes() == XML  # replication layer stripped


def test_load_config_none_when_disabled(tmp_path: Path) -> None:
    session_factory, crypto, _iid = _setup(tmp_path, enabled=False)
    assert load_config(session_factory, crypto) is None


def test_prepare_payload_refuses_double_encrypt_without_password() -> None:
    import pytest

    from worker.replication import ReplicationError, prepare_payload

    cfg = ReplicationConfig(
        enabled=True, kind="s3", base_path="x", encrypt_plaintext=True,
        double_encrypt=True, replication_password=None, mirror_deletes=False,
    )
    enc = encrypt_pfsense_backup(XML, INSTANCE_PW)
    with pytest.raises(ReplicationError):
        prepare_payload(enc, encrypted=True, compressed=False, cfg=cfg)
