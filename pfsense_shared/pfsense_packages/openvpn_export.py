"""Parses the OpenVPN Client Export package under
``<installedpackages><vpn_openvpn_export>``.

This package generates bundled OpenVPN client config files from the
firewall's configured OpenVPN servers. No credentials here directly —
the actual client configs are synthesised at export time and include
the server's TLS auth / CA refs by reference, which are already
redacted in their own sections. We surface the package's default
cert settings + its feature flags so operators can diff those across
backups.

v0.20.0 — also surfaces per-server overrides from
``<serverconfig><item>``. Operators often leave the top-level
``<defaults>`` untouched and adjust each server's export behaviour
individually; before v0.20.0 those overrides lived only in the raw
XML fallback. Security-relevant fields like ``blockoutsidedns`` and
``verifyservercn`` now diff cleanly in the structured view.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_sections._helpers import bool_flag, children, text


class OpenvpnClientExportServer(BaseModel):
    """Per-server override row under ``<serverconfig><item>``.

    Stable key: ``vpnid`` (matches the ``<vpnid>`` of an OpenVPN
    server defined under ``<openvpn>``). If absent, falls back to the
    item's index to keep diffs stable.
    """

    model_config = ConfigDict(extra="forbid")

    key: str
    vpnid: str | None = None
    # Security-relevant tunables.
    useaddr: str | None = None
    verifyservercn: str | None = None
    blockoutsidedns: bool = False
    usetoken: bool = False
    usepkcs11: bool = False
    bindmode: str | None = None
    silent_install: bool = False


class OpenvpnClientExportConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The OpenVPN Client Export "Advanced" page toggles.
    use_random_local_port: bool = False
    silent_install: bool = False
    interface_selection: str | None = None
    # Default cert / hostname fields for generated bundles.
    hostname: str | None = None
    ovpnexportcert: str | None = None
    ovpnexportcountry: str | None = None
    ovpnexportstate: str | None = None
    ovpnexportcity: str | None = None
    # v0.20.0 — per-server overrides.
    servers: list[OpenvpnClientExportServer] = []


CONSUMED_TAGS = frozenset({"vpn_openvpn_export", "openvpnexport"})


def _parse_server_rows(container: Element | None) -> list[OpenvpnClientExportServer]:
    if container is None:
        return []
    # Two shapes: ``<serverconfig><item>…</item></serverconfig>`` OR
    # ``<serverconfig><config>…</config></serverconfig>``. Older
    # builds also nested the rows directly under the package root.
    rows = children(container, "item")
    if not rows:
        rows = children(container, "config")
    out: list[OpenvpnClientExportServer] = []
    for i, row in enumerate(rows):
        vpnid = text(row, "vpnid")
        out.append(
            OpenvpnClientExportServer(
                key=vpnid or f"#{i}",
                vpnid=vpnid,
                useaddr=text(row, "useaddr"),
                verifyservercn=text(row, "verifyservercn"),
                blockoutsidedns=bool_flag(row, "blockoutsidedns"),
                usetoken=bool_flag(row, "usetoken"),
                usepkcs11=bool_flag(row, "usepkcs11"),
                bindmode=text(row, "bindmode"),
                silent_install=bool_flag(row, "silent_install"),
            )
        )
    return out


def parse(ip: Element) -> OpenvpnClientExportConfig | None:
    el = ip.find("vpn_openvpn_export")
    if el is None:
        el = ip.find("openvpnexport")
    if el is None:
        return None
    # Package XML variants place settings either at the top level or
    # under a ``<defaults>`` wrapper. The ``<serverconfig>`` block is
    # always a separate sibling carrying per-server rows. Explicit
    # ``is not None`` checks — ``el.find() or …`` relies on the
    # future-removed truth test on Element.
    defaults = el.find("defaults")
    srvcfg = el.find("serverconfig")
    inner = defaults if defaults is not None else el
    return OpenvpnClientExportConfig(
        use_random_local_port=bool_flag(inner, "use_random_local_port"),
        silent_install=bool_flag(inner, "silent_install"),
        interface_selection=text(inner, "interface_selection"),
        hostname=text(inner, "hostname"),
        ovpnexportcert=text(inner, "ovpnexportcert"),
        ovpnexportcountry=text(inner, "ovpnexportcountry"),
        ovpnexportstate=text(inner, "ovpnexportstate"),
        ovpnexportcity=text(inner, "ovpnexportcity"),
        servers=_parse_server_rows(srvcfg),
    )
