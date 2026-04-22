"""Public re-exports of label helpers from ``pfsense_diff``.

``pfsense_diff`` owns a catalogue of ``_label_*`` functions that
convert a row dict to a human-friendly one-liner (``"[wan] pass:
allow ssh"`` for a firewall rule, ``"DHCP: lan"`` for a DHCP server,
etc.). The diff viewer consumes them as ``label_fn`` callbacks.

The cumulative-changes endpoint needs the same labels per
``AnchorEvent`` row. Rather than duplicate the logic or take a
dependency on ``pfsense_diff``'s private surface, this module
re-exports each helper under a public name and offers
``label_for_section`` — a thin "section name → label function"
dispatcher keyed on the ``ConfigDiff`` field names.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# Private-symbol import is intentional: these functions are already
# battle-tested inside ``pfsense_diff`` and re-wiring their call
# sites would churn ~60 lines of that file with no semantic change.
# This module is the public façade; consumers never reach into
# ``pfsense_diff`` directly.
from .pfsense_diff import (
    _label_apikey as label_apikey,
)
from .pfsense_diff import (
    _label_bridge as label_bridge,
)
from .pfsense_diff import (
    _label_cron as label_cron,
)
from .pfsense_diff import (
    _label_csc as label_csc,
)
from .pfsense_diff import (
    _label_dhcp as label_dhcp,
)
from .pfsense_diff import (
    _label_dhcp_relay as label_dhcp_relay,
)
from .pfsense_diff import (
    _label_dyndns as label_dyndns,
)
from .pfsense_diff import (
    _label_firewall as label_firewall,
)
from .pfsense_diff import (
    _label_igmp as label_igmp,
)
from .pfsense_diff import (
    _label_interface as label_interface,
)
from .pfsense_diff import (
    _label_ipsec_p1 as label_ipsec_p1,
)
from .pfsense_diff import (
    _label_ipsec_p2 as label_ipsec_p2,
)
from .pfsense_diff import (
    _label_ipsec_psk as label_ipsec_psk,
)
from .pfsense_diff import (
    _label_lagg as label_lagg,
)
from .pfsense_diff import (
    _label_named as label_named,
)
from .pfsense_diff import (
    _label_nat as label_nat,
)
from .pfsense_diff import (
    _label_ovpn as label_ovpn,
)
from .pfsense_diff import (
    _label_pki as label_pki,
)
from .pfsense_diff import (
    _label_portal as label_portal,
)
from .pfsense_diff import (
    _label_ppp as label_ppp,
)
from .pfsense_diff import (
    _label_pppoe as label_pppoe,
)
from .pfsense_diff import (
    _label_proxyarp as label_proxyarp,
)
from .pfsense_diff import (
    _label_queue as label_queue,
)
from .pfsense_diff import (
    _label_radvd as label_radvd,
)
from .pfsense_diff import (
    _label_route as label_route,
)
from .pfsense_diff import (
    _label_sysctl as label_sysctl,
)
from .pfsense_diff import (
    _label_tunnel as label_tunnel,
)
from .pfsense_diff import (
    _label_vip as label_vip,
)
from .pfsense_diff import (
    _label_voucher as label_voucher,
)
from .pfsense_diff import (
    _label_wol as label_wol,
)

LabelFn = Callable[[dict[str, Any]], str]


LABEL_BY_SECTION: dict[str, LabelFn] = {
    "sysctl": label_sysctl,
    "cron": label_cron,
    "interfaces": label_interface,
    "vlans": label_named,
    "bridges": label_bridge,
    "gifs": label_tunnel,
    "gres": label_tunnel,
    "ppps": label_ppp,
    "qinqs": label_named,
    "laggs": label_lagg,
    "wol": label_wol,
    "gateways": label_named,
    "gateway_groups": label_named,
    "static_routes": label_route,
    "virtual_ips": label_vip,
    "firewall_rules": label_firewall,
    "nat_rules": label_nat,
    "aliases": label_named,
    "dyndns_entries": label_dyndns,
    "dhcp_servers": label_dhcp,
    "dhcp_relays": label_dhcp_relay,
    "schedules": label_named,
    "shaper_queues": label_queue,
    "dnshaper_pipes": label_named,
    "lb_pools": label_named,
    "lb_virtual_servers": label_named,
    "captive_portal_zones": label_portal,
    "igmpproxy_entries": label_igmp,
    "radvd_interfaces": label_radvd,
    "voucher_rolls": label_voucher,
    "openvpn_servers": label_ovpn,
    "openvpn_clients": label_ovpn,
    "openvpn_cscs": label_csc,
    "ipsec_phase1": label_ipsec_p1,
    "ipsec_phase2": label_ipsec_p2,
    "ipsec_psks": label_ipsec_psk,
    "certificate_authorities": label_pki,
    "certificates": label_pki,
    "crls": label_pki,
    "users": label_named,
    "groups": label_named,
    "authservers": label_named,
    "proxyarp": label_proxyarp,
    "interface_groups": label_named,
    "apikeys": label_apikey,
    "pppoe_servers": label_pppoe,
}


def label_for_section(section_name: str, row: dict[str, Any]) -> str:
    """Best-effort human label for a row dict in the named section.

    Falls back to ``label_named`` for unknown sections — which
    gracefully handles dicts with a ``name`` or ``key`` field and
    returns ``"?"`` otherwise.
    """
    fn = LABEL_BY_SECTION.get(section_name, label_named)
    try:
        return fn(row)
    except Exception:
        # Defensive: row shapes from backfill can occasionally lack
        # expected fields (corrupted data, legacy formats). Return a
        # placeholder rather than failing the whole response.
        return "?"


__all__ = [
    "LABEL_BY_SECTION",
    "LabelFn",
    "label_apikey",
    "label_bridge",
    "label_cron",
    "label_csc",
    "label_dhcp",
    "label_dhcp_relay",
    "label_dyndns",
    "label_firewall",
    "label_for_section",
    "label_igmp",
    "label_interface",
    "label_ipsec_p1",
    "label_ipsec_p2",
    "label_ipsec_psk",
    "label_lagg",
    "label_named",
    "label_nat",
    "label_ovpn",
    "label_pki",
    "label_portal",
    "label_ppp",
    "label_pppoe",
    "label_proxyarp",
    "label_queue",
    "label_radvd",
    "label_route",
    "label_sysctl",
    "label_tunnel",
    "label_vip",
    "label_voucher",
    "label_wol",
]
