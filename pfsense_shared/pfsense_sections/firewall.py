"""Parses ``<filter>`` — firewall rules (per-interface + floating).

pfSense evaluates rules top-to-bottom per-interface; order matters.
Each rule gets its ``tracker`` (pfSense-assigned) as its stable key.
When a rule is missing a tracker (very old configs), we fall back to a
content-hash so the diff still matches sensibly.
"""

from __future__ import annotations

import hashlib
from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from ._helpers import bool_flag, children, text


class Endpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    any_: bool = False
    network: str | None = None  # "lan", "wan", or a subnet literal
    address: str | None = None  # literal host / alias
    port: str | None = None
    not_: bool = False


class FirewallRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    tracker: str | None = None
    type: str | None = None  # pass | block | reject
    interface: str | None = None
    ipprotocol: str | None = None  # inet | inet6 | inet46
    protocol: str | None = None  # tcp | udp | tcp/udp | icmp | any
    source: Endpoint = Endpoint()
    destination: Endpoint = Endpoint()
    descr: str | None = None
    disabled: bool = False
    log: bool = False
    statetype: str | None = None
    gateway: str | None = None
    schedule: str | None = None
    floating: bool = False


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


def _rule_key(r: Element) -> str:
    tracker = text(r, "tracker")
    if tracker:
        return f"tracker:{tracker}"
    # Fallback: hash of the fields we care about — good enough to match
    # "same rule, slightly tweaked" across backups on pre-tracker configs.
    blob = "\x1f".join(
        [
            text(r, "descr") or "",
            text(r, "type") or "",
            text(r, "interface") or "",
            text(r, "protocol") or "",
        ]
    )
    return "hash:" + hashlib.sha1(blob.encode(), usedforsecurity=False).hexdigest()[:12]


def parse(root: Element) -> list[FirewallRule]:
    f_el = root.find("filter")
    if f_el is None:
        return []
    out: list[FirewallRule] = []
    for r in children(f_el, "rule"):
        out.append(
            FirewallRule(
                key=_rule_key(r),
                tracker=text(r, "tracker"),
                type=text(r, "type"),
                interface=text(r, "interface"),
                ipprotocol=text(r, "ipprotocol"),
                protocol=text(r, "protocol"),
                source=_endpoint(r.find("source")),
                destination=_endpoint(r.find("destination")),
                descr=text(r, "descr"),
                disabled=bool_flag(r, "disabled"),
                log=bool_flag(r, "log"),
                statetype=text(r, "statetype"),
                gateway=text(r, "gateway"),
                schedule=text(r, "sched"),
                floating=text(r, "floating") == "yes",
            )
        )
    return out
