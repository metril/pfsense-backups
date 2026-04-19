"""Encrypt/decrypt helpers for pfSense diag_backup.php encrypted config files.

pfSense wraps the ciphertext with:

    ---- BEGIN config.xml ----
    Version: <pfsense-version>
    Cipher: AES-256-CBC
    Hash: SHA256

    <base64 of "Salted__<8-byte salt><ciphertext>">
    ---- END config.xml ----

Two KDFs exist in the wild:

* **pfSense 2.7+** — PBKDF2-SHA256, 100 000 iterations, 48-byte derived
  output split as 32-byte key + 16-byte IV.
* **pfSense ≤ 2.6** — OpenSSL's legacy ``EVP_BytesToKey`` with MD5 over
  ``password || salt``.

Decrypt picks the KDF based on the ``Hash:`` header when present, with a
fallback attempt on the opposite KDF so we can still read pre-2.7
backups that shipped without the header. Encrypt always emits the 2.7+
PBKDF2-SHA256 format.

Used from both the worker (re-encrypt jobs) and the web service
(in-memory decrypt for View XML / Diff / Download).
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
from dataclasses import dataclass

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# PBKDF2 parameters pfSense 2.7+ uses. Iteration count is hard-coded in
# their config.lib.inc; changing this would silently break decryption.
_PBKDF2_ITERATIONS = 100_000
_KEY_BYTES = 32  # AES-256
_IV_BYTES = 16   # AES block size
_SALT_BYTES = 8
_SALT_PREFIX = b"Salted__"

# Canonical wrapper markers produced by pfSense's tagfile_reformat().
_BEGIN = "---- BEGIN config.xml ----"
_END = "---- END config.xml ----"
# The version we stamp into re-encrypted files. Not parsed by pfSense on
# import; it just wants the Cipher/Hash lines to match.
_ENCRYPT_VERSION = "2.7.2"


class PfSenseCryptoError(Exception):
    """Raised for malformed wrappers, bad passwords, or mismatched KDFs."""


@dataclass(frozen=True)
class _Parsed:
    headers: dict[str, str]
    body_b64: str


def _parse_wrapper(blob: bytes | str) -> _Parsed:
    text = blob.decode("utf-8", errors="replace") if isinstance(blob, bytes) else blob
    # Strip a BOM if pfSense's HTTP layer slipped one in.
    text = text.lstrip("\ufeff")

    begin_idx = text.find(_BEGIN)
    end_idx = text.find(_END)
    if begin_idx < 0 or end_idx < 0 or end_idx < begin_idx:
        raise PfSenseCryptoError("encrypted blob missing BEGIN/END markers")

    inner = text[begin_idx + len(_BEGIN) : end_idx]

    headers: dict[str, str] = {}
    body_lines: list[str] = []
    in_headers = True
    saw_header = False
    for raw_line in inner.splitlines():
        line = raw_line.strip()
        if in_headers:
            if not line:
                # A leading blank line sits between BEGIN and the first
                # header in some pfSense versions; only treat a blank as
                # the header/body separator *after* we've seen a header.
                if saw_header:
                    in_headers = False
                continue
            if ":" in line and not _is_base64_only(line):
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
                saw_header = True
                continue
            # Header-less encode that starts straight with base64.
            in_headers = False
            body_lines.append(line)
            continue
        if line:
            body_lines.append(line)

    body = "".join(body_lines)
    if not body:
        raise PfSenseCryptoError("encrypted blob has no base64 body")
    return _Parsed(headers=headers, body_b64=body)


_BASE64_LINE_RE = re.compile(r"^[A-Za-z0-9+/=]+$")


def _is_base64_only(line: str) -> bool:
    """True when *line* contains only base64 characters (no stray ``:``)."""
    return bool(_BASE64_LINE_RE.match(line))


def _split_salted(raw: bytes) -> tuple[bytes, bytes]:
    if len(raw) < len(_SALT_PREFIX) + _SALT_BYTES + 16:
        raise PfSenseCryptoError("ciphertext too short to contain Salted__ header")
    if not raw.startswith(_SALT_PREFIX):
        raise PfSenseCryptoError("ciphertext missing Salted__ prefix")
    salt = raw[len(_SALT_PREFIX) : len(_SALT_PREFIX) + _SALT_BYTES]
    ciphertext = raw[len(_SALT_PREFIX) + _SALT_BYTES :]
    if len(ciphertext) % 16 != 0:
        raise PfSenseCryptoError("ciphertext length not a multiple of AES block size")
    return salt, ciphertext


def _derive_pbkdf2_sha256(password: bytes, salt: bytes) -> tuple[bytes, bytes]:
    kdf = PBKDF2HMAC(
        algorithm=SHA256(),
        length=_KEY_BYTES + _IV_BYTES,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    out = kdf.derive(password)
    return out[:_KEY_BYTES], out[_KEY_BYTES : _KEY_BYTES + _IV_BYTES]


def _derive_evp_bytestokey_md5(password: bytes, salt: bytes) -> tuple[bytes, bytes]:
    """OpenSSL's legacy EVP_BytesToKey with MD5 — for pfSense ≤ 2.6."""
    needed = _KEY_BYTES + _IV_BYTES
    derived = b""
    last = b""
    while len(derived) < needed:
        last = hashlib.md5(last + password + salt).digest()
        derived += last
    return derived[:_KEY_BYTES], derived[_KEY_BYTES : _KEY_BYTES + _IV_BYTES]


def _aes_cbc_decrypt(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def _aes_cbc_encrypt(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def _looks_like_xml(data: bytes) -> bool:
    head = data[:256].lstrip()
    return head.startswith(b"<?xml") or head.startswith(b"<pfsense")


_KDF_PBKDF2 = "pbkdf2"
_KDF_MD5 = "md5"


def _pick_kdf_order(headers: dict[str, str]) -> tuple[str, str]:
    """Return (primary, fallback) KDF names based on the wrapper headers.

    pfSense 2.7+ emits ``Hash: SHA256``; older releases omit the header
    or don't include Hash at all. When we don't know, try PBKDF2 first
    (matches modern pfSense) and fall back to MD5.
    """
    hash_hint = headers.get("hash", "").lower()
    if "sha" in hash_hint:
        return _KDF_PBKDF2, _KDF_MD5
    if "md5" in hash_hint:
        return _KDF_MD5, _KDF_PBKDF2
    return _KDF_PBKDF2, _KDF_MD5


def decrypt_pfsense_backup(blob: bytes | str, password: str) -> bytes:
    """Decrypt a pfSense diag_backup.php encrypted blob into raw config.xml.

    Accepts either the full wrapped response body or the already-parsed
    base64 payload. Tries the KDF signaled by the wrapper headers first
    and falls back to the other KDF on unpad/plausibility failure so
    stored backups from pre-2.7 pfSense still decrypt.

    Returns the XML bytes. Caller is responsible for `.decode("utf-8")`.
    """
    parsed = _parse_wrapper(blob)
    try:
        raw = base64.b64decode(parsed.body_b64, validate=False)
    except Exception as exc:
        raise PfSenseCryptoError(f"base64 decode failed: {exc}") from exc

    salt, ciphertext = _split_salted(raw)
    pw_bytes = password.encode("utf-8")

    primary, fallback = _pick_kdf_order(parsed.headers)

    last_exc: Exception | None = None
    for kdf_name in (primary, fallback):
        derive = (
            _derive_pbkdf2_sha256 if kdf_name == _KDF_PBKDF2 else _derive_evp_bytestokey_md5
        )
        try:
            key, iv = derive(pw_bytes, salt)
            plaintext = _aes_cbc_decrypt(key, iv, ciphertext)
        except Exception as exc:
            last_exc = exc
            continue
        # Valid PKCS7 padding doesn't guarantee a correct password —
        # but a wrong password almost never produces plausible XML.
        if _looks_like_xml(plaintext):
            return plaintext
        last_exc = PfSenseCryptoError(
            f"{kdf_name} decryption produced non-XML output (wrong password?)"
        )

    assert last_exc is not None
    if isinstance(last_exc, PfSenseCryptoError):
        raise last_exc
    raise PfSenseCryptoError(f"decrypt failed: {last_exc}") from last_exc


def encrypt_pfsense_backup(xml: bytes | str, password: str) -> bytes:
    """Encrypt XML with the pfSense 2.7+ wrapper format.

    Emits the same ``---- BEGIN config.xml ----`` envelope pfSense
    produces, using PBKDF2-SHA256 (100 000 iters) + AES-256-CBC. Output
    is UTF-8 text wrapped in bytes so callers can write it straight to
    disk alongside non-encrypted backups.
    """
    plaintext = xml.encode("utf-8") if isinstance(xml, str) else xml
    salt = os.urandom(_SALT_BYTES)
    key, iv = _derive_pbkdf2_sha256(password.encode("utf-8"), salt)
    ciphertext = _aes_cbc_encrypt(key, iv, plaintext)
    body = _SALT_PREFIX + salt + ciphertext
    b64 = base64.b64encode(body).decode("ascii")
    # Match pfSense's line-wrapping at 76 chars so the file round-trips
    # through text-mode tools cleanly.
    wrapped = "\n".join(re.findall(r".{1,76}", b64))
    return (
        f"{_BEGIN}\n"
        f"Version: {_ENCRYPT_VERSION}\n"
        f"Cipher: AES-256-CBC\n"
        f"Hash: SHA256\n"
        f"\n"
        f"{wrapped}\n"
        f"{_END}\n"
    ).encode()


def looks_encrypted(blob: bytes | str) -> bool:
    """Cheap check for the BEGIN marker — used to decide if we need to decrypt."""
    if isinstance(blob, bytes):
        # Only peek at the head; encrypted blobs are small enough that
        # scanning 4 KiB is effectively free and covers any leading BOM
        # or whitespace pfSense's HTTP layer may inject.
        return _BEGIN.encode("utf-8") in blob[:4096]
    return _BEGIN in blob[:4096]
