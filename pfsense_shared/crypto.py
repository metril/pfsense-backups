"""Fernet-based encryption for pfSense credentials at rest."""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet


def ensure_key(key_file: Path) -> bytes:
    """Read the Fernet key from disk, generating it (0600) on first boot."""
    if key_file.exists():
        return key_file.read_bytes()
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    key_file.write_bytes(key)
    os.chmod(key_file, 0o600)
    return key


class Crypto:
    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    @classmethod
    def from_file(cls, key_file: Path) -> Crypto:
        return cls(ensure_key(key_file))

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        return self._fernet.decrypt(ciphertext).decode("utf-8")
