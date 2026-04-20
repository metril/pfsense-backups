"""Parses ``<sshdata>`` — persisted SSH host keys for the firewall.

pfSense stores its OpenSSH host keys (one pair per algorithm) in
config.xml so they survive firmware upgrades. The private halves
are full unencrypted OpenSSH keys — losing them to a leaked parsed
JSON or a diff render would re-key the server's identity for every
ops tool that's pinned to its fingerprint. Every ``*_key`` value is
redacted here; the ``*_key_pub`` counterparts are public material
and left visible so operators can still spot a host-key rotation
in a diff.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact

from ._helpers import text


class SshData(BaseModel):
    """SSH host-key material extracted from ``<sshdata>``.

    The four algorithms covered here are everything modern pfSense
    builds write; DSA is kept for legacy configs but the daemon
    won't use it on current releases. All private keys redact.
    """

    model_config = ConfigDict(extra="forbid")

    rsa_key: str | None = None
    rsa_key_pub: str | None = None
    ecdsa_key: str | None = None
    ecdsa_key_pub: str | None = None
    ed25519_key: str | None = None
    ed25519_key_pub: str | None = None
    dsa_key: str | None = None
    dsa_key_pub: str | None = None


def parse(root: Element) -> SshData | None:
    el = root.find("sshdata")
    if el is None:
        return None
    # pfSense's serializer uses one child per key type. Redact every
    # private half; the ``_pub`` halves are publishable.
    return SshData(
        rsa_key=redact("ssh_rsa_key", text(el, "ssh_rsa_key")),
        rsa_key_pub=text(el, "ssh_rsa_key_pub"),
        ecdsa_key=redact("ssh_ecdsa_key", text(el, "ssh_ecdsa_key")),
        ecdsa_key_pub=text(el, "ssh_ecdsa_key_pub"),
        ed25519_key=redact("ssh_ed25519_key", text(el, "ssh_ed25519_key")),
        ed25519_key_pub=text(el, "ssh_ed25519_key_pub"),
        dsa_key=redact("ssh_dsa_key", text(el, "ssh_dsa_key")),
        dsa_key_pub=text(el, "ssh_dsa_key_pub"),
    )
