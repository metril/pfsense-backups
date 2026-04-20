"""Parses ``<sshdata>`` — persisted SSH host-key material.

pfSense stores its OpenSSH host keys in config.xml as a list of
``<sshkeyfile>`` entries, each with:

  <sshkeyfile>
    <filename>ssh_host_rsa_key</filename>
    <xmldata>...base64+gzip blob of the key bytes...</xmldata>
  </sshkeyfile>

The entry whose ``<filename>`` ends in ``.pub`` holds the public
half (publishable); its sibling (same stem, no ``.pub``) is the
private key — redact.

Earlier shapes from legacy builds (per-algorithm elements like
``<ssh_rsa_key>`` directly under ``<sshdata>``) exist in some very
old backups — we read those too as a fallback so pre-pfSense-2.5
backups keep parsing.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact

from ._helpers import children, text


class SshHostKeyFile(BaseModel):
    """One half of an SSH host key (either the private or public side).

    The ``xmldata`` field is the base64-encoded gzip'd key bytes as
    pfSense emits them. For private halves it redacts; for
    ``.pub`` halves it stays visible so a key rotation still shows
    up in diffs."""

    model_config = ConfigDict(extra="forbid")

    filename: str
    is_private: bool
    # The actual key material. Private → REDACTED; public → raw blob.
    xmldata: str | None = None


class SshData(BaseModel):
    """SSH host keys surfaced as a list of filename-keyed entries.
    Legacy keys (DSA) and modern ones (ed25519, ecdsa, rsa) are all
    covered without the parser caring about the algorithm set."""

    model_config = ConfigDict(extra="forbid")

    keys: list[SshHostKeyFile] = []


def _is_public_filename(filename: str) -> bool:
    # pfSense's sshd host-key filenames follow the OpenSSH convention
    # ``ssh_host_{algo}_key`` + a sibling ``ssh_host_{algo}_key.pub``.
    return filename.endswith(".pub")


def parse(root: Element) -> SshData | None:
    el = root.find("sshdata")
    if el is None:
        return None

    keys: list[SshHostKeyFile] = []

    # Modern shape: ``<sshkeyfile>`` entries.
    for f in children(el, "sshkeyfile"):
        name = text(f, "filename") or ""
        if not name:
            continue
        is_pub = _is_public_filename(name)
        raw = text(f, "xmldata")
        keys.append(
            SshHostKeyFile(
                filename=name,
                is_private=not is_pub,
                xmldata=(
                    raw
                    if is_pub
                    else redact(_redact_tag_for_filename(name), raw)
                ),
            )
        )

    # Pre-2.5 legacy shape: per-algorithm elements directly under
    # ``<sshdata>``. Read both private (``ssh_rsa_key``) and public
    # (``ssh_rsa_key_pub``) names; surface them as keyfile entries so
    # the UI renders them uniformly.
    for algo in ("rsa", "ecdsa", "ed25519", "dsa"):
        priv = text(el, f"ssh_{algo}_key")
        if priv:
            keys.append(
                SshHostKeyFile(
                    filename=f"ssh_host_{algo}_key",
                    is_private=True,
                    xmldata=redact(f"ssh_{algo}_key", priv),
                )
            )
        pub = text(el, f"ssh_{algo}_key_pub")
        if pub:
            keys.append(
                SshHostKeyFile(
                    filename=f"ssh_host_{algo}_key.pub",
                    is_private=False,
                    xmldata=pub,
                )
            )

    if not keys:
        return None
    return SshData(keys=keys)


def _redact_tag_for_filename(filename: str) -> str:
    """Map ``ssh_host_rsa_key`` → the ``_EXACT`` tag name that redacts
    it. Falls through to a generic ``_privkey`` suffix for algorithms
    we don't anticipate."""
    # Strip ``ssh_host_`` prefix and the trailing ``_key`` to get the
    # algorithm; compose the legacy-style tag name that's already in
    # ``_EXACT`` (``ssh_rsa_key``, ``ssh_ecdsa_key``, …).
    lower = filename.lower()
    if lower.startswith("ssh_host_") and lower.endswith("_key"):
        algo = lower[len("ssh_host_") : -len("_key")]
        return f"ssh_{algo}_key"
    # Anything unusual — fall back to a suffix-matched redaction tag.
    return "ssh_host_privkey"
