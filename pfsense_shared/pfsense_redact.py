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
        "pre-shared-key",
        "pre_shared_key",
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
        "trapstring",  # SNMP trap community string (pfSense's field name)
        "pskey",
        "psk",
        "auth_token",
        "api_key",
        "apikey",
        "api_token",
        "apitoken",
        "accountkey",
        "account_key",
        "user_key",
        "userkey",
        "webhook_url",
        "webhookurl",
        "oinkcode",
        "maxmind_key",
        "nas_secret",
        "shared_secret",
        "user_password",
        "proxy_auth_password",
        "influxdb_token",
        # ACME DNS-01 provider credentials stored under
        # <a_domainlist><item>. Today's parser reads only <name> +
        # <method> and silently drops sibling credential tags, so
        # these never reach JSON output — but any future parser
        # revision that surfaces <item> child text would leak the
        # tokens without redaction. Added defensively. ``_SUFFIXES``
        # already catches ``*_secret_key`` / ``*_access_key`` /
        # ``*_api_key`` variants; only ``_token`` / ``_api_key``
        # without the ``_`` prefix fall through, so we name them
        # explicitly here.
        "cf_token",
        "cf_key",
        "do_api_key",
        "gd_key",
        "gd_secret",
        # Telegraf → InfluxDB username. Not a password by itself, but
        # the operator's login identity on the metrics backend — enough
        # to phish a password out of or to check membership in breach
        # corpora. Redacted alongside its paired password/token.
        "influxdb_username",
        # Squid NTLM auth — ``<nt_pass>`` stores the domain-join
        # password for Windows auth. Does not match the ``_password``
        # suffix because the field name isn't literally ``nt_password``.
        "nt_pass",
        "frr_password",
        "bgp_password",
        "ospf_password",
        "secret",
        # pfSense's NUT / apcupsd "remote monitor" password — the
        # attribute name lacks the underscore that the generic
        # ``*_password`` suffix would match, so it gets an exact entry.
        "remotepassword",
        # pfSense's Zabbix package stores the TLS pre-shared key under
        # <tlspsk>; <tls_psk> is the normalised form some parsers use.
        "tlspsk",
        "tls_psk",
        # SSH host private keys persisted in ``<sshdata>``. Leaking any
        # of these would re-key the firewall's host identity across
        # every known-host pin in the ops tooling.
        "ssh_rsa_key",
        "ssh_ecdsa_key",
        "ssh_ed25519_key",
        "ssh_dsa_key",
        # pfSense's ``<apikeys>`` ships web-UI API tokens inline.
        "apikey_secret",
        "api_secret",
        # WireGuard private keys — the interface key identifies the
        # tunnel endpoint and is as sensitive as a TLS private key.
        # pfSense stores both interface and peer private keys under
        # the same tag name; the peer preshared-key falls back to the
        # existing ``presharedkey`` / ``psk`` entries above.
        "privatekey",
        "private_key",
        # NOTE: "token" intentionally NOT in _EXACT. Bare ``<token>``
        # appears in benign contexts (e.g. third-party package revision
        # counters), so we only redact explicit API-token fields via
        # ``api_token`` / ``apitoken`` / ``auth_token`` / the
        # ``*_authtoken`` suffix. DynDNS providers that emit a bare
        # ``<token>`` element redact at the call site via
        # ``redact("api_token", …)``.
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
