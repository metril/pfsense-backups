"""Parses ACME (Let's Encrypt / acme.sh) config under ``<installedpackages>``.

Account keys are opaque PEM blobs and DNS API configs hold provider
credentials (Cloudflare tokens, Route53 keys, etc.). Both surface as
redacted lock icons; the raw XML tab remains the escape hatch.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact
from pfsense_shared.pfsense_sections._helpers import bool_flag, children, text


class AcmeAccountKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    descr: str | None = None
    acmeserver: str | None = None
    email: str | None = None
    # Redacted — PEM-encoded private key.
    accountkey: str | None = None


class AcmeCertificate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    acmeaccount: str | None = None
    keylength: str | None = None
    preferredchain: str | None = None
    ocspstaple: bool = False
    dnssleep: str | None = None
    # Comma-joined list of SAN entries for quick readability.
    san_list: list[str] = []
    renewafter: str | None = None


class AcmeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enable: bool = False
    writecert_log: bool = False
    account_keys: list[AcmeAccountKey] = []
    certificates: list[AcmeCertificate] = []


CONSUMED_TAGS = frozenset({"acme"})


def _san_list(cert: Element) -> list[str]:
    """Collect SAN rows into a list like ``domain (method)``."""
    out: list[str] = []
    block = cert.find("a_domainlist")
    if block is None:
        return out
    for item in children(block, "item"):
        host = text(item, "name")
        method = text(item, "method")
        if host:
            out.append(f"{host} ({method})" if method else host)
    return out


def parse(ip: Element) -> AcmeConfig | None:
    root = ip.find("acme")
    if root is None:
        return None

    account_keys: list[AcmeAccountKey] = []
    keys_block = root.find("accountkeys")
    if keys_block is not None:
        for k in children(keys_block, "item"):
            name = text(k, "name")
            if not name:
                continue
            account_keys.append(
                AcmeAccountKey(
                    name=name,
                    descr=text(k, "descr"),
                    acmeserver=text(k, "acmeserver"),
                    email=text(k, "email"),
                    accountkey=redact("accountkey", text(k, "accountkey")),
                )
            )

    certificates: list[AcmeCertificate] = []
    certs_block = root.find("certificates")
    if certs_block is not None:
        for c in children(certs_block, "item"):
            name = text(c, "name")
            if not name:
                continue
            certificates.append(
                AcmeCertificate(
                    name=name,
                    acmeaccount=text(c, "acmeaccount"),
                    keylength=text(c, "keylength"),
                    preferredchain=text(c, "preferredchain"),
                    ocspstaple=bool_flag(c, "ocspstaple"),
                    dnssleep=text(c, "dnssleep"),
                    san_list=_san_list(c),
                    renewafter=text(c, "renewafter"),
                )
            )

    return AcmeConfig(
        enable=bool_flag(root, "enable"),
        writecert_log=bool_flag(root, "writecert_log"),
        account_keys=account_keys,
        certificates=certificates,
    )
