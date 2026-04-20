"""Parses the OpenVPN Client Export package under
``<installedpackages><vpn_openvpn_export>``.

This package generates bundled OpenVPN client config files from the
firewall's configured OpenVPN servers. No credentials here directly —
the actual client configs are synthesised at export time and include
the server's TLS auth / CA refs by reference, which are already
redacted in their own sections. We surface the package's default
cert settings + its feature flags so operators can diff those across
backups.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_sections._helpers import bool_flag, text


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


CONSUMED_TAGS = frozenset({"vpn_openvpn_export", "openvpnexport"})


def parse(ip: Element) -> OpenvpnClientExportConfig | None:
    el = ip.find("vpn_openvpn_export")
    if el is None:
        el = ip.find("openvpnexport")
    if el is None:
        return None
    # Package XML variants place settings either at the top level or
    # under a single ``<defaults>`` / ``<serverconfig>`` wrapper. Try
    # each in order and fall back to the outer element. Explicit
    # ``is not None`` checks — ``el.find() or …`` relies on the
    # future-removed truth test on Element.
    defaults = el.find("defaults")
    srvcfg = el.find("serverconfig")
    inner = defaults if defaults is not None else (srvcfg if srvcfg is not None else el)
    return OpenvpnClientExportConfig(
        use_random_local_port=bool_flag(inner, "use_random_local_port"),
        silent_install=bool_flag(inner, "silent_install"),
        interface_selection=text(inner, "interface_selection"),
        hostname=text(inner, "hostname"),
        ovpnexportcert=text(inner, "ovpnexportcert"),
        ovpnexportcountry=text(inner, "ovpnexportcountry"),
        ovpnexportstate=text(inner, "ovpnexportstate"),
        ovpnexportcity=text(inner, "ovpnexportcity"),
    )
