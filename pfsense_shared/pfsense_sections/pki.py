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


class CertificateAuthority(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refid: str
    descr: str | None = None
    crt: str | None = None  # base64-encoded public cert
    prv: str | None = None  # redacted private key
    serial: str | None = None


class Certificate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refid: str
    descr: str | None = None
    caref: str | None = None  # which CA signed this
    type: str | None = None  # "server" | "user" | "self-signed"
    crt: str | None = None
    prv: str | None = None  # redacted


def parse_cas(root: Element) -> list[CertificateAuthority]:
    out: list[CertificateAuthority] = []
    for ca in children(root, "ca"):
        refid = text(ca, "refid")
        if not refid:
            continue
        out.append(
            CertificateAuthority(
                refid=refid,
                descr=text(ca, "descr"),
                crt=text(ca, "crt"),
                prv=redact("prv", text(ca, "prv")),
                serial=text(ca, "serial"),
            )
        )
    return out


def parse_certs(root: Element) -> list[Certificate]:
    out: list[Certificate] = []
    for c in children(root, "cert"):
        refid = text(c, "refid")
        if not refid:
            continue
        out.append(
            Certificate(
                refid=refid,
                descr=text(c, "descr"),
                caref=text(c, "caref"),
                type=text(c, "type"),
                crt=text(c, "crt"),
                prv=redact("prv", text(c, "prv")),
            )
        )
    return out
