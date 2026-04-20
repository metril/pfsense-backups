"""Small, best-effort X.509 decoder used by ``pki.py``.

pfSense stores certificates in ``config.xml`` as base64-encoded PEM
text — i.e. the ``<crt>`` element contains base64 of a PEM block
(with ``-----BEGIN CERTIFICATE-----`` markers). Decoding gives us the
PEM text, which ``cryptography.x509`` can parse.

The decoder is deliberately forgiving: any failure path returns
``None`` so a malformed or unusual cert never breaks the structured
view for the rest of the backup. The raw base64 body stays on the
parsed record (non-secret), so the UI can still fall back to showing
the blob when decode fails.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Final

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import ExtensionOID, NameOID
from pydantic import BaseModel, ConfigDict


class CertMetadata(BaseModel):
    """Human-readable slice of an X.509 certificate."""

    model_config = ConfigDict(extra="forbid")

    subject_cn: str | None = None
    subject: str | None = None  # RFC4514 form, e.g. "CN=gw,O=corp"
    issuer_cn: str | None = None
    issuer: str | None = None
    serial_hex: str | None = None
    not_before: datetime | None = None
    not_after: datetime | None = None
    sans: list[str] = []
    # SHA-256 fingerprint, lowercase hex, colon-separated per pair
    fingerprint_sha256: str | None = None


_PEM_HEADER: Final[bytes] = b"-----BEGIN CERTIFICATE-----"


def _decode_b64_to_pem(raw: str) -> bytes | None:
    """pfSense's ``<crt>`` is base64 of PEM bytes. Decode and sanity-check.

    Falls back to treating ``raw`` as already-PEM text when either
    (a) base64 decoding fails with a padding / malformed error, or
    (b) base64 decoding succeeds but the result isn't a PEM block.
    Older pfSense revisions sometimes store the cert as raw PEM.
    """
    try:
        decoded = base64.b64decode(raw, validate=False)
    except (ValueError, binascii.Error):
        decoded = b""
    if _PEM_HEADER in decoded:
        return decoded
    pem = raw.encode("utf-8", errors="replace")
    if _PEM_HEADER in pem:
        return pem
    return None


def _name_cn(name: x509.Name) -> str | None:
    attrs = name.get_attributes_for_oid(NameOID.COMMON_NAME)
    if not attrs:
        return None
    value = attrs[0].value
    return value if isinstance(value, str) else value.decode("utf-8", "replace")


def _sans(cert: x509.Certificate) -> list[str]:
    try:
        ext = cert.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
    except x509.ExtensionNotFound:
        return []
    san = ext.value
    if not isinstance(san, x509.SubjectAlternativeName):
        return []
    out: list[str] = []
    for entry in san:
        # Normalise the common flavours into a single prefix-tagged string.
        if isinstance(entry, x509.DNSName):
            out.append(f"DNS:{entry.value}")
        elif isinstance(entry, x509.IPAddress):
            out.append(f"IP:{entry.value}")
        elif isinstance(entry, x509.RFC822Name):
            out.append(f"email:{entry.value}")
        elif isinstance(entry, x509.UniformResourceIdentifier):
            out.append(f"URI:{entry.value}")
        else:
            out.append(str(entry))
    return out


def _fingerprint(cert: x509.Certificate) -> str:
    digest = cert.fingerprint(hashes.SHA256()).hex()
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))


def decode(raw: str | None) -> CertMetadata | None:
    """Decode pfSense's ``<crt>`` blob into structured metadata.

    ``raw`` is the string contents of the ``<crt>`` element — either
    base64-encoded PEM (standard) or raw PEM (pfSense quirk). Returns
    ``None`` on any parse failure; upstream code treats missing
    metadata as "still show the raw blob, just no nice subject/expiry
    overlay".
    """
    if not raw or not raw.strip():
        return None
    pem = _decode_b64_to_pem(raw.strip())
    if pem is None:
        return None
    try:
        cert = x509.load_pem_x509_certificate(pem)
    except (ValueError, TypeError):
        return None

    try:
        not_before = cert.not_valid_before_utc
        not_after = cert.not_valid_after_utc
    except AttributeError:
        # cryptography < 42 exposed the aware variants under different names.
        not_before = cert.not_valid_before
        not_after = cert.not_valid_after

    return CertMetadata(
        subject_cn=_name_cn(cert.subject),
        subject=cert.subject.rfc4514_string(),
        issuer_cn=_name_cn(cert.issuer),
        issuer=cert.issuer.rfc4514_string(),
        serial_hex=format(cert.serial_number, "x"),
        not_before=not_before,
        not_after=not_after,
        sans=_sans(cert),
        fingerprint_sha256=_fingerprint(cert),
    )
