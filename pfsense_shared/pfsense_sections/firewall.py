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


def _endpoint_blob(el: Element | None) -> str:
    """Flatten a ``<source>`` / ``<destination>`` subtree into a stable
    tuple string for use in ``_rule_key``. Mirrors
    ``nat._endpoint_blob`` so two rules with different targets on the
    same interface produce distinct fallback keys without leaning on
    ``<descr>``."""
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


def _rule_key(r: Element) -> str:
    tracker = text(r, "tracker")
    if tracker:
        return f"tracker:{tracker}"
    # Fallback for pre-tracker configs: content-hash of the
    # *functional* fields so editing ``<descr>`` (or ``<log>``, which
    # only toggles telemetry) doesn't fork the blame history into a
    # remove+add event pair. Fields included are those that change
    # how the rule evaluates traffic:
    #   - type, interface, ipprotocol, protocol: the packet-matching
    #     filter itself.
    #   - source / destination blobs: the match criteria.
    #   - gateway: policy-based routing destination.
    #   - disabled: whether the rule fires at all.
    #   - floating + direction: whether the rule lives in per-
    #     interface or floating ruleset, and its direction
    #     (``in``/``out``/``any``) when floating. Toggling either
    #     changes evaluation order meaningfully.
    #   - statetype: ``keep state`` vs ``none`` vs ``synproxy`` —
    #     different state-tracking behaviour is functionally a
    #     different rule.
    # ``<descr>``, ``<log>``, ``<created>`` / ``<updated>``, and
    # ``<associated-rule-id>`` are deliberately EXCLUDED (cosmetic
    # / metadata / volatile). Same reasoning as NAT (see nat._key).
    blob = "\x1f".join(
        [
            text(r, "type") or "",
            text(r, "interface") or "",
            text(r, "ipprotocol") or "",
            text(r, "protocol") or "",
            _endpoint_blob(r.find("source")),
            _endpoint_blob(r.find("destination")),
            text(r, "gateway") or "",
            text(r, "disabled") or "",
            text(r, "floating") or "",
            text(r, "direction") or "",
            text(r, "statetype") or "",
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
