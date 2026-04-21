"""Tests for the v0.36.0 MultiFernet-based Crypto class + the
``ensure_keys`` / ``write_keys`` file helpers.

Rotation end-to-end (secret-key file → re-encrypt rows → prune) is
exercised via the worker CLI test in ``tests/worker/test_key_rotation_cli.py``.
This file pins the primitives those flows lean on.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from cryptography.fernet import Fernet, InvalidToken

from pfsense_shared.crypto import Crypto, ensure_keys, write_keys


def test_single_key_encrypt_roundtrip() -> None:
    key = Fernet.generate_key()
    c = Crypto(key)
    token = c.encrypt("hello")
    assert c.decrypt(token) == "hello"


def test_accepts_list_of_keys_uses_first_for_encryption() -> None:
    """First key in the list is the current encryption key.
    ``MultiFernet.encrypt`` always encrypts with ``_fernets[0]``."""
    new_key = Fernet.generate_key()
    old_key = Fernet.generate_key()
    c = Crypto([new_key, old_key])
    token = c.encrypt("payload")

    # The fresh output decrypts under the new key on its own.
    assert Crypto(new_key).decrypt(token) == "payload"
    # And not under only the old key.
    with pytest.raises(InvalidToken):
        Crypto(old_key).decrypt(token)


def test_multifernet_decrypts_legacy_ciphertext() -> None:
    """A ciphertext produced under the OLD key still decrypts via a
    ``Crypto`` holding ``[new, old]`` — that's the whole point of
    key rotation."""
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    legacy_token = Fernet(old_key).encrypt(b"rotate-me")
    c_multi = Crypto([new_key, old_key])
    assert c_multi.decrypt(legacy_token) == "rotate-me"


def test_rotate_via_encrypt_produces_fresh_ciphertext_under_new_key() -> None:
    """Simulates the rotation loop's inner step: decrypt with
    MultiFernet, re-encrypt with the new key. The refreshed token
    must decrypt under the new key ALONE once the old key is
    pruned from the file."""
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    legacy_token = Fernet(old_key).encrypt(b"secret")

    c_multi = Crypto([new_key, old_key])
    plaintext = c_multi.decrypt(legacy_token)
    refreshed = c_multi.encrypt(plaintext)

    # Pruned world — only the new key in play.
    c_new_only = Crypto(new_key)
    assert c_new_only.decrypt(refreshed) == "secret"
    # And the OLD key has no use anymore.
    with pytest.raises(InvalidToken):
        Crypto(old_key).decrypt(refreshed)


def test_empty_keys_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        Crypto([])


def test_ensure_keys_first_boot_generates_0600_file(tmp_path: Path) -> None:
    f = tmp_path / "secret.key"
    keys = ensure_keys(f)
    assert len(keys) == 1
    assert Fernet(keys[0])  # valid Fernet key

    mode = stat.S_IMODE(os.stat(f).st_mode)
    assert mode == 0o600, f"expected 0600 permissions, got {oct(mode)}"


def test_ensure_keys_reads_multi_line_file(tmp_path: Path) -> None:
    """Multi-key file (post-rotation transitional state) parses as
    a list in file order. Blank lines + whitespace are ignored."""
    k1 = Fernet.generate_key()
    k2 = Fernet.generate_key()
    k3 = Fernet.generate_key()
    f = tmp_path / "secret.key"
    # Deliberately messy: blank line, trailing whitespace, no trailing newline.
    f.write_bytes(k1 + b"\n\n  " + k2 + b"  \n" + k3)
    assert ensure_keys(f) == [k1, k2, k3]


def test_ensure_keys_single_line_legacy_file(tmp_path: Path) -> None:
    """Pre-v0.36.0 deployments have a single-line secret-key file
    with (likely) a trailing newline. Must still parse as a
    one-element list."""
    k = Fernet.generate_key()
    f = tmp_path / "secret.key"
    f.write_bytes(k + b"\n")
    assert ensure_keys(f) == [k]


def test_ensure_keys_rejects_empty_file(tmp_path: Path) -> None:
    f = tmp_path / "secret.key"
    f.write_bytes(b"\n\n\n")
    with pytest.raises(ValueError, match="empty"):
        ensure_keys(f)


def test_write_keys_preserves_0600_permissions(tmp_path: Path) -> None:
    f = tmp_path / "secret.key"
    k1 = Fernet.generate_key()
    k2 = Fernet.generate_key()
    write_keys(f, [k1, k2])
    assert ensure_keys(f) == [k1, k2]

    mode = stat.S_IMODE(os.stat(f).st_mode)
    assert mode == 0o600


def test_write_keys_atomic_overwrite(tmp_path: Path) -> None:
    """``write_keys`` goes through a ``.tmp`` sibling + ``os.replace``
    so a partial write (disk full, crash) can't leave the real file
    empty or truncated."""
    f = tmp_path / "secret.key"
    k1 = Fernet.generate_key()
    write_keys(f, [k1])

    k2 = Fernet.generate_key()
    write_keys(f, [k2, k1])
    # The tmp sibling must be gone — atomic rename consumed it.
    assert not f.with_suffix(f.suffix + ".tmp").exists()
    assert ensure_keys(f) == [k2, k1]


def test_write_keys_rejects_empty_list(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty"):
        write_keys(tmp_path / "secret.key", [])
