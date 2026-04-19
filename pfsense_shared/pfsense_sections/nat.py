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
    kind: str  # "port_forward" | "one_to_one" | "outbound"
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


def _key(r: Element, kind: str) -> str:
    blob = "\x1f".join(
        [
            kind,
            text(r, "descr") or "",
            text(r, "interface") or "",
            text(r, "target") or "",
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

    return out
