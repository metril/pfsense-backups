"""X.509 decoder tests + integration with pki.parse_certs.

Uses a real self-signed test cert stored as base64-wrapped PEM in
``fixtures/sample_cert_b64.txt`` — pfSense's on-disk format. The
cert has CN ``gw.lan.example``, organization ``TestCorp``, serial
``0xcafebabedeadbeef``, and three SAN DNS entries, valid
2024-01-01 → 2034-01-01.
"""

from __future__ import annotations

import textwrap
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pfsense_shared.pfsense_parser import parse
from pfsense_shared.pfsense_sections._x509 import decode

FIXTURE = (
    Path(__file__).parent / "fixtures" / "sample_cert_b64.txt"
)


@pytest.fixture(scope="module")
def cert_b64() -> str:
    return FIXTURE.read_text().strip()


def test_decode_fields(cert_b64: str) -> None:
    m = decode(cert_b64)
    assert m is not None
    assert m.subject_cn == "gw.lan.example"
    assert "CN=gw.lan.example" in (m.subject or "")
    assert "O=TestCorp" in (m.subject or "")
    # Self-signed: issuer == subject
    assert m.issuer_cn == m.subject_cn
    # Validity window
    assert m.not_before == datetime(2024, 1, 1, tzinfo=UTC)
    assert m.not_after == datetime(2034, 1, 1, tzinfo=UTC)
    # Serial is lowercase hex (no 0x prefix)
    assert m.serial_hex == "cafebabedeadbeef"
    # SANs normalised with DNS: prefix
    assert "DNS:gw.lan.example" in m.sans
    assert "DNS:gw" in m.sans
    assert "DNS:*.gw.lan.example" in m.sans
    # Fingerprint is colon-separated lowercase hex
    assert m.fingerprint_sha256 is not None
    assert len(m.fingerprint_sha256) == 64 + 31  # 32 bytes × 2 hex chars + 31 colons


def test_decode_none_on_malformed() -> None:
    assert decode(None) is None
    assert decode("") is None
    assert decode("not base64 at all") is None
    # Valid base64 but not a PEM cert
    import base64

    garbage_b64 = base64.b64encode(b"hello world").decode()
    assert decode(garbage_b64) is None


def test_decode_accepts_raw_pem_without_b64_wrapper(cert_b64: str) -> None:
    """Older pfSense revisions omit the outer base64 wrap. The decoder
    should still recognize the PEM block if it appears unwrapped."""
    import base64

    pem = base64.b64decode(cert_b64).decode()
    m = decode(pem)
    assert m is not None
    assert m.subject_cn == "gw.lan.example"


def test_pki_parse_populates_metadata(cert_b64: str) -> None:
    """End-to-end: an XML config with a <cert><crt>...</crt></cert>
    node should come out of parse() with decoded metadata on the
    Certificate entry."""
    xml = textwrap.dedent(f"""
        <pfsense>
          <cert>
            <refid>cert-abc</refid>
            <descr>gateway web cert</descr>
            <type>server</type>
            <crt>{cert_b64}</crt>
            <prv>LEAKED_PRV_KEY</prv>
          </cert>
          <ca>
            <refid>ca-abc</refid>
            <descr>self-signed CA</descr>
            <crt>{cert_b64}</crt>
            <prv>LEAKED_CA_KEY</prv>
          </ca>
        </pfsense>
    """).strip().encode()
    cfg = parse(xml)
    assert len(cfg.certificates) == 1
    cert = cfg.certificates[0]
    assert cert.metadata is not None
    assert cert.metadata.subject_cn == "gw.lan.example"
    assert cert.metadata.not_after == datetime(2034, 1, 1, tzinfo=UTC)
    assert "DNS:gw.lan.example" in cert.metadata.sans

    assert len(cfg.certificate_authorities) == 1
    ca = cfg.certificate_authorities[0]
    assert ca.metadata is not None
    assert ca.metadata.subject_cn == "gw.lan.example"

    # Private key still redacted (regression check)
    assert "LEAKED_PRV_KEY" not in cfg.model_dump_json()
    assert "LEAKED_CA_KEY" not in cfg.model_dump_json()


def test_pki_parse_tolerates_garbage_crt() -> None:
    """A malformed <crt> shouldn't blow up parsing — it should surface
    as metadata=None with the raw crt field still carried."""
    xml = textwrap.dedent("""
        <pfsense>
          <cert>
            <refid>bad-cert</refid>
            <descr>broken</descr>
            <crt>not-a-real-cert-blob</crt>
          </cert>
        </pfsense>
    """).strip().encode()
    cfg = parse(xml)
    assert len(cfg.certificates) == 1
    cert = cfg.certificates[0]
    assert cert.metadata is None
    assert cert.crt == "not-a-real-cert-blob"
