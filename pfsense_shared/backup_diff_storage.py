"""Helpers for writing + reading ``BackupDiff`` rows.

Shared between the worker (post-save diff writer) and the web app
(read endpoint + lazy recompute on staleness). Stays out of
``pfsense_shared/pfsense_diff.py`` to keep the pure parser /
semantic-diff code decoupled from storage concerns (DB, gzip, ORM).
"""

from __future__ import annotations

import gzip
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .pfsense_diff import ConfigDiff, SectionDiff, diff_configs
from .pfsense_parser import PfSenseParseError
from .pfsense_parser import parse as parse_pfsense_xml

if TYPE_CHECKING:
    from .crypto import Crypto

log = logging.getLogger(__name__)


def summarise_diff(diff: ConfigDiff) -> tuple[int, int, int]:
    """Roll up a ``ConfigDiff`` into ``(added, removed, modified)``
    totals. Mirrors the frontend ``summariseDiff`` helper so badge
    numbers on the timeline match what the full diff view would
    show."""
    added = removed = modified = 0
    for section_name in type(diff).model_fields:
        section = getattr(diff, section_name, None)
        if not isinstance(section, SectionDiff):
            continue
        added += len(section.added)
        removed += len(section.removed)
        modified += len(section.modified)
    return added, removed, modified


def encode_diff(diff: ConfigDiff) -> bytes:
    """Serialize + gzip a ConfigDiff for storage in ``full_diff_gz``.
    Pydantic's ``model_dump_json`` gives canonical JSON; gzip at
    level 6 (default) is a good size/time tradeoff — typical
    ConfigDiff compresses 4-6x."""
    raw = diff.model_dump_json().encode("utf-8")
    return gzip.compress(raw)


def decode_diff(blob: bytes) -> dict[str, Any]:
    """Ungzip + parse a ``full_diff_gz`` blob back into a plain dict.
    Returned as a dict rather than a ``ConfigDiff`` instance so the
    web endpoint can hand the payload straight to FastAPI's JSON
    encoder without re-serializing. Callers that actually need a
    typed ``ConfigDiff`` can round-trip via
    ``ConfigDiff.model_validate(dict)``."""
    import json
    from typing import cast

    raw = gzip.decompress(blob)
    return cast(dict[str, Any], json.loads(raw.decode("utf-8")))


def read_backup_bytes(
    path: Path,
    *,
    encrypted: bool,
    encrypt_password_ct: bytes | None,
    crypto: Crypto,
) -> bytes | None:
    """Read a backup file from disk, decrypting + decompressing as
    needed. Returns None on any read failure — callers treat this
    as "skip diff for this row" rather than propagating the error
    up into the backup pipeline."""
    from .pfsense_crypto import PfSenseCryptoError, decrypt_pfsense_backup

    try:
        if not path.exists():
            log.warning("backup file missing on disk: %s", path)
            return None
        raw = path.read_bytes()
    except OSError as exc:
        log.warning("failed to read backup file %s: %s", path, exc)
        return None

    if not encrypted:
        # read_content-style decompression: the worker stores gzip-
        # compressed files with the .gz extension; plain XML otherwise.
        if path.suffix == ".gz":
            try:
                return gzip.decompress(raw)
            except OSError as exc:
                log.warning("failed to gunzip %s: %s", path, exc)
                return None
        return raw

    if encrypt_password_ct is None:
        log.warning(
            "encrypted backup %s has no password ciphertext — skipping diff",
            path,
        )
        return None
    try:
        password = crypto.decrypt(encrypt_password_ct)
    except Exception as exc:
        # ERROR, not warning: the master key failing to open a stored
        # password ciphertext is systemic (key rotated without
        # re-encrypting, corrupted key file), unlike a single odd backup
        # file — operators must be able to tell the two apart in logs.
        log.error(
            "master key cannot decrypt the stored backup password for %s "
            "(possible key rotation issue — skipping diff): %s",
            path, exc,
        )
        return None
    try:
        return decrypt_pfsense_backup(raw, password)
    except PfSenseCryptoError as exc:
        log.warning("failed to decrypt backup %s: %s", path, exc)
        return None


def compute_diff(
    new_bytes: bytes,
    base_bytes: bytes,
) -> ConfigDiff | None:
    """Parse both backups and return a structured diff. Returns None
    if either side fails to parse (malformed XML, truncated file);
    caller treats that as "no diff" and moves on."""
    try:
        a_parsed = parse_pfsense_xml(base_bytes)
        b_parsed = parse_pfsense_xml(new_bytes)
    except PfSenseParseError as exc:
        log.warning("failed to parse XML for diff: %s", exc)
        return None
    return diff_configs(a_parsed, b_parsed)
