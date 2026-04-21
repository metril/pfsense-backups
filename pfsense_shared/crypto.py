"""Fernet-based encryption for pfSense credentials at rest.

Supports key rotation via ``MultiFernet``: the secret-key file may
contain one key per line, where the first line is the *current*
encryption key and any remaining lines are legacy keys retained only
for decryption. ``MultiFernet.decrypt`` walks the list in order and
returns the first successful decryption; ``encrypt`` always uses the
first (newest) key.

Invariant: operators produce a multi-key file only by running
``python -m worker rotate-key`` (or writing one manually for
disaster-recovery). The worker's rotation CLI re-encrypts every
stored ciphertext with the new key, then prunes the legacy keys
from the file so the steady-state file is always a single line.
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, MultiFernet


def ensure_keys(key_file: Path) -> list[bytes]:
    """Read the Fernet key(s) from disk, generating one (0o600) on
    first boot.

    File format: one base64 Fernet key per line. A single-line file
    (legacy, pre-v0.36.0) is returned as a one-element list. Empty
    lines are ignored. Leading / trailing whitespace is stripped.

    L1: Set a restrictive umask around the initial write so there
    is no window where the key exists on disk with world-readable
    permissions. The subsequent explicit ``chmod`` is belt-and-
    braces.
    """
    if key_file.exists():
        content = key_file.read_bytes()
        keys = [line.strip() for line in content.splitlines() if line.strip()]
        if not keys:
            raise ValueError(f"secret key file is empty: {key_file}")
        return keys
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    old_umask = os.umask(0o077)
    try:
        key_file.write_bytes(key + b"\n")
    finally:
        os.umask(old_umask)
    os.chmod(key_file, 0o600)
    return [key]


def ensure_key(key_file: Path) -> bytes:
    """Back-compat shim for callers that only need the current key
    (e.g. tests that pass a raw key to ``Crypto`` bypassing the
    file-backed path). Prefer ``ensure_keys`` in new code."""
    return ensure_keys(key_file)[0]


def write_keys(key_file: Path, keys: list[bytes]) -> None:
    """Atomically rewrite the secret-key file with the given keys,
    one per line. Used by the ``rotate-key`` worker CLI after a
    full re-encryption pass completes. Permissions stay at 0o600."""
    if not keys:
        raise ValueError("refusing to write an empty secret key file")
    body = b"\n".join(keys) + b"\n"
    tmp = key_file.with_suffix(key_file.suffix + ".tmp")
    old_umask = os.umask(0o077)
    try:
        tmp.write_bytes(body)
        os.chmod(tmp, 0o600)
        os.replace(tmp, key_file)
    finally:
        os.umask(old_umask)


class Crypto:
    """Thin wrapper around ``MultiFernet``. Accepts either a single
    key (bytes) or a list of keys — the first is the current
    encryption key, the rest are legacy-decrypt-only."""

    def __init__(self, keys: bytes | list[bytes]) -> None:
        if isinstance(keys, (bytes, bytearray)):
            key_list: list[bytes] = [bytes(keys)]
        else:
            key_list = list(keys)
        if not key_list:
            raise ValueError("Crypto requires at least one Fernet key")
        self._fernets = [Fernet(k) for k in key_list]
        self._multi = MultiFernet(self._fernets)

    @classmethod
    def from_file(cls, key_file: Path) -> Crypto:
        return cls(ensure_keys(key_file))

    def encrypt(self, plaintext: str) -> bytes:
        return self._multi.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        return self._multi.decrypt(ciphertext).decode("utf-8")
