"""Parses the PKI store: ``<ca>`` (certificate authorities) and
``<cert>`` (user-provided and self-signed certificates).

Private keys are redacted; public cert blobs are surfaced as-is so
operators can compare "which cert is installed" without having to
pull the raw XML. We don't currently try to parse the cert itself
(X.509 CN / SAN / expiry) — that's future work; the raw base64 is
opaque but at least the diff can detect "cert rotated".
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact

from ._helpers import children, text
from ._x509 import CertMetadata
from ._x509 import decode as decode_x509


class CertificateAuthority(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refid: str
    descr: str | None = None
    crt: str | None = None  # base64-encoded public cert
    prv: str | None = None  # redacted private key
    serial: str | None = None
    # Decoded X.509 overlay — CN, SAN, expiry, issuer, fingerprint.
    # ``None`` when the blob wasn't decodable (malformed or missing).
    metadata: CertMetadata | None = None


class Certificate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refid: str
    descr: str | None = None
    caref: str | None = None  # which CA signed this
    type: str | None = None  # "server" | "user" | "self-signed"
    crt: str | None = None
    prv: str | None = None  # redacted
    metadata: CertMetadata | None = None


class CertificateRevocationList(BaseModel):
    """pfSense Certificate Revocation List — ties to a CA via ``caref``.

    The UI surface is small (method=internal/existing, CRL descr, list
    of revoked cert refids with a reason code) but it completes the PKI
    review story: ops folks spot "cert X was revoked in yesterday's
    backup but not today's" which would otherwise be invisible.
    """

    model_config = ConfigDict(extra="forbid")

    refid: str
    descr: str | None = None
    caref: str | None = None  # which CA this CRL belongs to
    method: str | None = None  # "internal" | "existing" | "imported"
    lifetime: str | None = None
    serial: str | None = None
    # Revoked certs (by cert refid) + reason codes.
    revoked_cert_refids: list[str] = []
    # Raw CRL PEM text or base64. We don't attempt to parse it.
    text: str | None = None


def parse_cas(root: Element) -> list[CertificateAuthority]:
    out: list[CertificateAuthority] = []
    for ca in children(root, "ca"):
        refid = text(ca, "refid")
        if not refid:
            continue
        crt = text(ca, "crt")
        out.append(
            CertificateAuthority(
                refid=refid,
                descr=text(ca, "descr"),
                crt=crt,
                prv=redact("prv", text(ca, "prv")),
                serial=text(ca, "serial"),
                metadata=decode_x509(crt),
            )
        )
    return out


def parse_crls(root: Element) -> list[CertificateRevocationList]:
    out: list[CertificateRevocationList] = []
    for crl in children(root, "crl"):
        refid = text(crl, "refid")
        if not refid:
            continue
        revoked: list[str] = []
        for cert in children(crl, "cert"):
            rr = text(cert, "refid")
            if rr:
                revoked.append(rr)
        out.append(
            CertificateRevocationList(
                refid=refid,
                descr=text(crl, "descr"),
                caref=text(crl, "caref"),
                method=text(crl, "method"),
                lifetime=text(crl, "lifetime"),
                serial=text(crl, "serial"),
                revoked_cert_refids=revoked,
                text=text(crl, "text"),
            )
        )
    return out


def parse_certs(root: Element) -> list[Certificate]:
    out: list[Certificate] = []
    for c in children(root, "cert"):
        refid = text(c, "refid")
        if not refid:
            continue
        crt = text(c, "crt")
        out.append(
            Certificate(
                refid=refid,
                descr=text(c, "descr"),
                caref=text(c, "caref"),
                type=text(c, "type"),
                crt=crt,
                prv=redact("prv", text(c, "prv")),
                metadata=decode_x509(crt),
            )
        )
    return out
