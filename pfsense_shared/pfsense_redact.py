"""Redaction policy for pfSense config fields.

Secrets in config.xml (password hashes, cert private keys, PSKs, shared
secrets, SNMP communities) must not appear in the parsed JSON or in the
structured diff. Single source of truth lives here so every section
parser gets identical behaviour and adding a new rule is a one-line
change.

The raw XML tab in the UI is deliberately *not* affected — it remains
the escape hatch for operators who actually need the bytes (e.g. to
decrypt a backup offline or re-import into pfSense).
"""

from __future__ import annotations

import re
from typing import Final

REDACTED: Final[str] = "***redacted***"


# Exact tag names that always redact. Lowercase; match is case-insensitive
# against ``Element.tag.lower()`` in callers.
_EXACT: Final[frozenset[str]] = frozenset(
    {
        "password",
        "bcrypt_hash",
        "md5_hash",
        "presharedkey",
        "shared_key",
        "tls",
        "tls_auth",
        "prv",  # cert / CA private key
        "radius_secret",
        "radius_secret_enc",
        "ldap_bindpw",
        "bindpw",
        "rocommunity",
        "rwcommunity",
        "community",  # SNMPv1/v2c community
        "trap_community",
        "pskey",
        "psk",
        "auth_token",
        "api_key",
        "apikey",
        "secret",
    }
)


# Patterns that redact when the tag name *ends with* these suffixes. Covers
# the long tail of pfsense fields like ``radius_secret``, ``ldap_bindpw``,
# ``tls_client_key``, any ``*_password`` field in package configs, etc.
_SUFFIXES: Final[tuple[str, ...]] = (
    "_password",
    "_secret",
    "_privkey",
    "_private_key",
    "_bindpw",
    "_apikey",
    "_api_key",
    "_authtoken",
    "_auth_token",
)


# Compiled once at module load for perf — redact() is called on every leaf.
_SUFFIX_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:" + "|".join(re.escape(s) for s in _SUFFIXES) + r")\Z",
    re.IGNORECASE,
)


def should_redact(tag: str) -> bool:
    """Return True if a leaf whose tag is ``tag`` must be redacted.

    Tag comparison is case-insensitive; callers pass ``Element.tag`` as-is.
    """
    lower = tag.lower()
    if lower in _EXACT:
        return True
    return _SUFFIX_RE.search(lower) is not None


def redact(tag: str, value: str | None) -> str | None:
    """Return REDACTED placeholder for secret fields, else pass ``value`` through.

    Falsy values (empty string, None) are returned as-is so the diff
    still shows "was unset, now set" without forcing a redact token into
    every empty field.
    """
    if value in (None, ""):
        return value
    if should_redact(tag):
        return REDACTED
    return value
