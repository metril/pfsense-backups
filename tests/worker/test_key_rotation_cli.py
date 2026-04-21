"""End-to-end test for the ``python -m worker rotate-key``
subcommand. Seeds a SQLite DB with Instance + Backup rows whose
ciphertext columns are encrypted under an OLD key, runs the
rotation function in-process (no subprocess — reuses the same
engine), and verifies:

- Every ciphertext column now decrypts under the NEW key alone.
- The secret-key file is back to a single line (legacy keys pruned).
- Plaintext values survived the round-trip unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pfsense_shared.crypto import Crypto, ensure_keys, write_keys
from pfsense_shared.models import Backup, Base, Instance


def _seed(session_factory, crypto: Crypto) -> tuple[int, int]:
    """Insert one Instance (with all three ciphertext columns) and
    one Backup (with ``encrypt_password_ct``) encrypted under the
    given ``Crypto``. Returns ``(instance_id, backup_id)`` so the
    test can re-read them."""
    with session_factory() as s:
        inst = Instance(
            name="gw-rotate",
            url="https://gw.rotate.test",
            username_ct=crypto.encrypt("admin"),
            password_ct=crypto.encrypt("hunter2"),
            subfolder=None,
            backup_prefix="daily",
            verify_ssl=False,
            timeout_seconds=30,
            enabled=True,
            retention_count=10,
            backup_encrypt=True,
            backup_encrypt_password_ct=crypto.encrypt("backup-pass"),
        )
        s.add(inst)
        s.commit()
        s.refresh(inst)

        bkp = Backup(
            instance_id=inst.id,
            started_at=datetime(2026, 4, 1, tzinfo=UTC),
            finished_at=datetime(2026, 4, 1, tzinfo=UTC),
            duration_seconds=1.0,
            filename="daily_gw.xml",
            path="/tmp/daily_gw.xml",
            size_bytes=1,
            compressed=False,
            success=True,
            encrypted=True,
            encrypt_password_ct=crypto.encrypt("per-row-password"),
        )
        s.add(bkp)
        s.commit()
        s.refresh(bkp)
        return inst.id, bkp.id


def test_rotate_key_end_to_end(tmp_path: Path, monkeypatch) -> None:
    # Point the WorkerSettings file location at a temp key file, and
    # the DB URL at a sqlite file under tmp_path. ``WorkerSettings``
    # reads both from env vars with sensible defaults.
    key_file = tmp_path / "secret.key"
    db_file = tmp_path / "app.db"
    db_url = f"sqlite:///{db_file}"

    monkeypatch.setenv("PFSENSE_BACKUPS_SECRET_KEY_FILE", str(key_file))
    monkeypatch.setenv("APP_DB_URL", db_url)
    # WorkerSettings also requires a ZMQ bind; give it a UDS under tmp.
    monkeypatch.setenv("ZMQ_PULL_BIND", f"ipc://{tmp_path / 'pull.sock'}")
    monkeypatch.setenv("ZMQ_PUB_BIND", f"ipc://{tmp_path / 'pub.sock'}")

    # Seed the key file with ONE initial key (pre-rotation state).
    old_key = Fernet.generate_key()
    write_keys(key_file, [old_key])

    # Bring up Base on the sqlite file. ``rotate_key`` calls
    # ``init_db`` itself, but seeding via a second engine is cleanest.
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False, future=True)
    crypto_old = Crypto(old_key)
    inst_id, bkp_id = _seed(session_factory, crypto_old)
    engine.dispose()

    # Run rotation.
    from worker.__main__ import rotate_key

    rc = rotate_key()
    assert rc == 0, "rotate_key CLI returned non-zero exit code"

    # Post-rotation file has exactly one key, and it is NOT the old key.
    post_keys = ensure_keys(key_file)
    assert len(post_keys) == 1
    new_key = post_keys[0]
    assert new_key != old_key

    # Every ciphertext now decrypts under the NEW key alone.
    crypto_new = Crypto(new_key)
    engine2 = create_engine(db_url, future=True)
    factory2 = sessionmaker(engine2, expire_on_commit=False, future=True)
    with factory2() as s:
        inst = s.execute(select(Instance).where(Instance.id == inst_id)).scalar_one()
        assert crypto_new.decrypt(inst.username_ct) == "admin"
        assert crypto_new.decrypt(inst.password_ct) == "hunter2"
        assert inst.backup_encrypt_password_ct is not None
        assert (
            crypto_new.decrypt(inst.backup_encrypt_password_ct) == "backup-pass"
        )

        bkp = s.execute(select(Backup).where(Backup.id == bkp_id)).scalar_one()
        assert bkp.encrypt_password_ct is not None
        assert crypto_new.decrypt(bkp.encrypt_password_ct) == "per-row-password"
    engine2.dispose()


def test_rotate_key_idempotent_when_no_legacy_keys(
    tmp_path: Path, monkeypatch
) -> None:
    """Running ``rotate-key`` twice in a row works — the second run
    simply generates another fresh key and re-encrypts everything
    again. No rows are lost."""
    key_file = tmp_path / "secret.key"
    db_file = tmp_path / "app.db"
    db_url = f"sqlite:///{db_file}"

    monkeypatch.setenv("PFSENSE_BACKUPS_SECRET_KEY_FILE", str(key_file))
    monkeypatch.setenv("APP_DB_URL", db_url)
    monkeypatch.setenv("ZMQ_PULL_BIND", f"ipc://{tmp_path / 'pull.sock'}")
    monkeypatch.setenv("ZMQ_PUB_BIND", f"ipc://{tmp_path / 'pub.sock'}")

    old_key = Fernet.generate_key()
    write_keys(key_file, [old_key])

    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False, future=True)
    inst_id, _ = _seed(session_factory, Crypto(old_key))
    engine.dispose()

    from worker.__main__ import rotate_key

    assert rotate_key() == 0
    key_after_first = ensure_keys(key_file)[0]
    assert rotate_key() == 0
    key_after_second = ensure_keys(key_file)[0]
    assert key_after_first != key_after_second

    # Verify the row still decrypts under the final key.
    engine2 = create_engine(db_url, future=True)
    factory2 = sessionmaker(engine2, expire_on_commit=False, future=True)
    with factory2() as s:
        inst = s.execute(select(Instance).where(Instance.id == inst_id)).scalar_one()
        crypto_final = Crypto(key_after_second)
        assert crypto_final.decrypt(inst.username_ct) == "admin"
    engine2.dispose()
