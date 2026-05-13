"""Parses ``<nat>`` — port-forward, 1:1, outbound rules."""

from __future__ import annotations

import hashlib
from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from ._helpers import bool_flag, children, text
from .firewall import Endpoint


class NatRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    kind: str  # "port_forward" | "one_to_one" | "outbound" | "npt"
    interface: str | None = None
    protocol: str | None = None
    source: Endpoint = Endpoint()
    destination: Endpoint = Endpoint()
    target: str | None = None
    local_port: str | None = None
    descr: str | None = None
    disabled: bool = False


def _endpoint(el: Element | None) -> Endpoint:
    if el is None:
        return Endpoint()
    return Endpoint(
        any_=el.find("any") is not None,
        network=text(el, "network"),
        address=text(el, "address"),
        port=text(el, "port"),
        not_=el.find("not") is not None,
    )


def _endpoint_blob(el: Element | None) -> str:
    """Flatten a ``<source>`` or ``<destination>`` subtree into a
    stable tuple string. Used by ``_key`` — including the endpoint
    fields makes two port-forward rules on the same interface with
    different address/port targets distinguishable without relying
    on descriptions."""
    if el is None:
        return ""
    return "|".join(
        [
            "any" if el.find("any") is not None else "",
            text(el, "network") or "",
            text(el, "address") or "",
            text(el, "port") or "",
            "not" if el.find("not") is not None else "",
        ]
    )


def _key(r: Element, kind: str) -> str:
    """Synthesize a stable per-rule key.

    v0.40.0: derived from the fields that functionally define a NAT
    rule — interface, protocol, source, destination, target, and
    local port. The rule description (``<descr>``) is deliberately
    EXCLUDED: it's a user-facing label that operators edit for
    clarity, and including it would force every description tweak
    to emit a bogus add+remove event pair in the blame log (each
    tweak produces a fresh key, so the projector sees an old rule
    disappearing and a new one appearing).

    Two NAT rules that share all functional fields AND a kind but
    differ only in description still collide under this scheme,
    which is correct — they're the same logical rule. The rare case
    of intentionally-duplicate rules with different descriptions
    (a pfSense anti-pattern anyway) gets merged in blame history;
    operators fix that by making the target or port distinct.
    """
    blob = "\x1f".join(
        [
            kind,
            text(r, "interface") or "",
            text(r, "protocol") or "",
            _endpoint_blob(r.find("source")),
            _endpoint_blob(r.find("destination")),
            text(r, "target") or "",
            text(r, "external") or "",  # 1:1 NAT uses <external>
            text(r, "local-port") or "",
        ]
    )
    return "hash:" + hashlib.sha1(blob.encode(), usedforsecurity=False).hexdigest()[:12]


def parse(root: Element) -> list[NatRule]:
    nat_el = root.find("nat")
    if nat_el is None:
        return []
    out: list[NatRule] = []

    # Port forwards (<rule> children at top level of <nat>).
    for r in children(nat_el, "rule"):
        out.append(
            NatRule(
                key=_key(r, "port_forward"),
                kind="port_forward",
                interface=text(r, "interface"),
                protocol=text(r, "protocol"),
                source=_endpoint(r.find("source")),
                destination=_endpoint(r.find("destination")),
                target=text(r, "target"),
                local_port=text(r, "local-port"),
                descr=text(r, "descr"),
                disabled=bool_flag(r, "disabled"),
            )
        )

    # 1:1.
    for r in children(nat_el, "onetoone"):
        out.append(
            NatRule(
                key=_key(r, "one_to_one"),
                kind="one_to_one",
                interface=text(r, "interface"),
                source=_endpoint(r.find("source")),
                destination=_endpoint(r.find("destination")),
                target=text(r, "external"),
                descr=text(r, "descr"),
                disabled=bool_flag(r, "disabled"),
            )
        )

    # Outbound — pfSense wraps these in <outbound><rule>...</rule></outbound>.
    outbound = nat_el.find("outbound")
    if outbound is not None:
        for r in children(outbound, "rule"):
            out.append(
                NatRule(
                    key=_key(r, "outbound"),
                    kind="outbound",
                    interface=text(r, "interface"),
                    protocol=text(r, "protocol"),
                    source=_endpoint(r.find("source")),
                    destination=_endpoint(r.find("destination")),
                    target=text(r, "target"),
                    descr=text(r, "descr"),
                    disabled=bool_flag(r, "disabled"),
                )
            )

    # NPt (Network Prefix Translation, IPv6). pfSense stores each
    # entry as a <npt> child of <nat> with <interface>, a source IPv6
    # prefix in <source>/<address> (or <src>), a destination IPv6
    # prefix in <destination>/<address> (or <dst>), plus <descr> /
    # <disabled>. Previously dropped entirely — entire NAT kind was
    # invisible in the structured view.
    for r in children(nat_el, "npt"):
        src_addr = (
            text(r.find("source"), "address") if r.find("source") is not None else None
        ) or text(r, "src")
        dst_addr = (
            text(r.find("destination"), "address")
            if r.find("destination") is not None
            else None
        ) or text(r, "dst")
        out.append(
            NatRule(
                key=_key(r, "npt"),
                kind="npt",
                interface=text(r, "interface"),
                source=Endpoint(address=src_addr) if src_addr else Endpoint(),
                destination=Endpoint(address=dst_addr) if dst_addr else Endpoint(),
                descr=text(r, "descr"),
                disabled=bool_flag(r, "disabled"),
            )
        )

    return out
