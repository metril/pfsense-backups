"""Parses ``<gateways>`` and ``<staticroutes>``.

Gateways are keyed by ``name``; static routes are keyed by
``(network, gateway)``.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from ._helpers import bool_flag, children, text


class Gateway(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    interface: str | None = None
    gateway: str | None = None
    ipprotocol: str | None = None  # inet | inet6
    monitor: str | None = None
    descr: str | None = None
    weight: str | None = None
    defaultgw: bool = False
    disabled: bool = False
    # v0.42.0 — gateway monitoring thresholds. pfSense uses dpinger
    # against ``monitor``; these tune what counts as a degraded gateway
    # (used by gateway groups for failover) and how often it probes.
    # Previously silently dropped — operators couldn't see their tuning.
    latencylow: str | None = None
    latencyhigh: str | None = None
    losslow: str | None = None
    losshigh: str | None = None
    interval: str | None = None
    time_period: str | None = None
    alert_interval: str | None = None
    loss_interval: str | None = None
    data_payload: str | None = None
    force_down: bool = False


class GatewayGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    descr: str | None = None
    trigger: str | None = None
    # Members are a list of "gateway_name|tier" strings in the raw XML; we
    # expose the tier-ordered list of names for readability.
    members: list[str] = []


class StaticRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    network: str | None = None
    gateway: str | None = None
    descr: str | None = None
    disabled: bool = False


def parse_gateways(root: Element) -> tuple[list[Gateway], list[GatewayGroup]]:
    el = root.find("gateways")
    if el is None:
        return [], []
    gws: list[Gateway] = []
    for item in children(el, "gateway_item"):
        name = text(item, "name")
        if not name:
            continue
        gws.append(
            Gateway(
                name=name,
                interface=text(item, "interface"),
                gateway=text(item, "gateway"),
                ipprotocol=text(item, "ipprotocol"),
                monitor=text(item, "monitor"),
                descr=text(item, "descr"),
                weight=text(item, "weight"),
                defaultgw=bool_flag(item, "defaultgw"),
                disabled=bool_flag(item, "disabled"),
                latencylow=text(item, "latencylow"),
                latencyhigh=text(item, "latencyhigh"),
                losslow=text(item, "losslow"),
                losshigh=text(item, "losshigh"),
                interval=text(item, "interval"),
                time_period=text(item, "time_period"),
                alert_interval=text(item, "alert_interval"),
                loss_interval=text(item, "loss_interval"),
                data_payload=text(item, "data_payload"),
                force_down=bool_flag(item, "force_down"),
            )
        )
    groups: list[GatewayGroup] = []
    for item in children(el, "gateway_group"):
        gname = text(item, "name")
        if not gname:
            continue
        members: list[str] = []
        for m in children(item, "item"):
            if m.text:
                members.append(m.text)
        groups.append(
            GatewayGroup(
                name=gname,
                descr=text(item, "descr"),
                trigger=text(item, "trigger"),
                members=members,
            )
        )
    return gws, groups


def parse_static_routes(root: Element) -> list[StaticRoute]:
    el = root.find("staticroutes")
    if el is None:
        return []
    out: list[StaticRoute] = []
    for item in children(el, "route"):
        network = text(item, "network")
        gateway = text(item, "gateway")
        key = f"{network or ''}|{gateway or ''}"
        out.append(
            StaticRoute(
                key=key,
                network=network,
                gateway=gateway,
                descr=text(item, "descr"),
                disabled=bool_flag(item, "disabled"),
            )
        )
    return out
