"""Tests for v0.17.0 — six new package parsers + metadata ignores.

Each parser gets a structure test (does it produce the expected
Pydantic shape from realistic XML) plus, where applicable, a
``LEAKY_*`` secret-leak check against ``cfg.model_dump_json()`` to
prove redaction is wired correctly.
"""

from __future__ import annotations

import textwrap

from pfsense_shared.pfsense_parser import parse
from pfsense_shared.pfsense_redact import REDACTED


def _parse(xml: str):
    return parse(textwrap.dedent(xml).strip().encode())


# ---------- WireGuard -------------------------------------------------------


WIREGUARD_XML = """
<pfsense>
  <installedpackages>
    <wireguard>
      <tunnels>
        <item>
          <name>wg0</name>
          <descr>site-to-site</descr>
          <enabled>yes</enabled>
          <listenport>51820</listenport>
          <mtu>1420</mtu>
          <address>10.7.0.1/24</address>
          <publickey>PUBLIC_KEY_OK_TO_EXPOSE</publickey>
          <privatekey>LEAKY_WG_PRIVATE_KEY</privatekey>
        </item>
      </tunnels>
      <peers>
        <item>
          <descr>remote-office</descr>
          <enabled>yes</enabled>
          <tun>wg0</tun>
          <endpoint>203.0.113.7</endpoint>
          <port>51820</port>
          <persistentkeepalive>25</persistentkeepalive>
          <allowedips>10.7.0.2/32, 192.168.50.0/24</allowedips>
          <publickey>PEER_PUBLIC_KEY</publickey>
          <presharedkey>LEAKY_WG_PSK</presharedkey>
        </item>
      </peers>
    </wireguard>
  </installedpackages>
</pfsense>
"""


def test_wireguard_structure_and_redaction():
    cfg = _parse(WIREGUARD_XML)
    pkgs = cfg.installedpackages
    assert pkgs is not None
    wg = pkgs.wireguard
    assert wg is not None

    assert len(wg.tunnels) == 1
    t = wg.tunnels[0]
    assert t.name == "wg0"
    assert t.enabled is True
    assert t.listen_port == "51820"
    assert t.addresses == ["10.7.0.1/24"]
    # Public key survives verbatim (not a secret).
    assert t.public_key == "PUBLIC_KEY_OK_TO_EXPOSE"
    # Private key is redacted — only the redaction marker leaves the parser.
    assert t.private_key == REDACTED

    assert len(wg.peers) == 1
    p = wg.peers[0]
    assert p.tun == "wg0"
    assert p.endpoint == "203.0.113.7"
    assert p.allowed_ips == ["10.7.0.2/32", "192.168.50.0/24"]
    assert p.public_key == "PEER_PUBLIC_KEY"
    assert p.preshared_key == REDACTED

    dumped = cfg.model_dump_json()
    assert "LEAKY_WG_PRIVATE_KEY" not in dumped
    assert "LEAKY_WG_PSK" not in dumped
    # Non-sensitive keys still reach the UI.
    assert "PUBLIC_KEY_OK_TO_EXPOSE" in dumped
    assert "PEER_PUBLIC_KEY" in dumped


def test_wireguard_bare_tag_still_produces_config():
    """An operator with WireGuard installed but no tunnels / peers
    configured still sees the package in the viewer."""
    cfg = _parse(
        "<pfsense><installedpackages><wireguard/></installedpackages></pfsense>"
    )
    pkgs = cfg.installedpackages
    assert pkgs is not None
    assert pkgs.wireguard is not None
    assert pkgs.wireguard.tunnels == []
    assert pkgs.wireguard.peers == []


# ---------- Snort / snortglobal ---------------------------------------------


SNORT_XML = """
<pfsense>
  <installedpackages>
    <snortglobal>
      <oinkcode>LEAKY_SNORT_OINKCODE</oinkcode>
      <snortcommunityrules>on</snortcommunityrules>
      <emergingthreats>on</emergingthreats>
    </snortglobal>
    <snort>
      <rule>
        <item>
          <uuid>iface-uuid-1</uuid>
          <interface>wan</interface>
          <descr>WAN</descr>
          <enable>on</enable>
          <blockoffenders7>on</blockoffenders7>
          <ips_mode>ips_mode_inline</ips_mode>
          <rulesets>emerging-exploit.rules||emerging-dos.rules</rulesets>
        </item>
        <item>
          <uuid>iface-uuid-2</uuid>
          <interface>lan</interface>
          <enable>off</enable>
        </item>
      </rule>
    </snort>
  </installedpackages>
</pfsense>
"""


def test_snort_structure_and_oinkcode_redaction():
    cfg = _parse(SNORT_XML)
    pkgs = cfg.installedpackages
    assert pkgs is not None
    sn = pkgs.snort
    assert sn is not None
    # Oinkcode surfaced as a presence boolean, never as plaintext.
    assert sn.oinkmaster_configured is True
    assert sn.snort_community_rules_enabled is True
    assert sn.emerging_threats_enabled is True
    assert len(sn.interfaces) == 2
    wan = sn.interfaces[0]
    assert wan.interface == "wan"
    assert wan.enable is True
    assert wan.blockoffenders is True
    assert wan.ips_mode == "ips_mode_inline"
    assert "emerging-exploit.rules" in wan.categories
    assert "emerging-dos.rules" in wan.categories

    # Oinkcode leak check — the plaintext must never land in the
    # parsed JSON tree.
    assert "LEAKY_SNORT_OINKCODE" not in cfg.model_dump_json()


# ---------- miniUPnPd -------------------------------------------------------


def test_miniupnpd_structure():
    xml = """
    <pfsense>
      <installedpackages>
        <miniupnpd>
          <enable>on</enable>
          <enable_upnp>on</enable_upnp>
          <enable_natpmp>on</enable_natpmp>
          <iface_array>lan,opt1</iface_array>
          <ext_iface>wan</ext_iface>
          <download>100000</download>
          <upload>50000</upload>
          <permit1>allow 1024-65535 192.168.1.0/24 1024-65535</permit1>
          <permit2>deny 0-65535 0.0.0.0/0 0-65535</permit2>
        </miniupnpd>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    pkgs = cfg.installedpackages
    assert pkgs is not None
    up = pkgs.miniupnpd
    assert up is not None
    assert up.enable is True
    assert up.enable_upnp is True
    assert up.enable_natpmp is True
    assert up.iface_array == "lan,opt1"
    assert up.ext_iface == "wan"
    assert up.download == "100000"
    assert len(up.permit_rules) == 2
    assert up.permit_rules[0].startswith("allow 1024-65535")


# ---------- Avahi -----------------------------------------------------------


def test_avahi_structure():
    xml = """
    <pfsense>
      <installedpackages>
        <avahi>
          <enable>on</enable>
          <enable_reflector>on</enable_reflector>
          <interfaces>lan,dmz</interfaces>
        </avahi>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    pkgs = cfg.installedpackages
    assert pkgs is not None
    av = pkgs.avahi
    assert av is not None
    assert av.enable is True
    assert av.reflector is True
    assert av.interfaces == "lan,dmz"


# ---------- OpenVPN Client Export -------------------------------------------


def test_openvpn_client_export_structure():
    xml = """
    <pfsense>
      <installedpackages>
        <vpn_openvpn_export>
          <defaults>
            <use_random_local_port>on</use_random_local_port>
            <hostname>vpn.example.com</hostname>
            <ovpnexportcountry>US</ovpnexportcountry>
            <ovpnexportstate>CA</ovpnexportstate>
            <ovpnexportcity>SanFrancisco</ovpnexportcity>
          </defaults>
        </vpn_openvpn_export>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    pkgs = cfg.installedpackages
    assert pkgs is not None
    ovx = pkgs.openvpn_client_export
    assert ovx is not None
    assert ovx.use_random_local_port is True
    assert ovx.hostname == "vpn.example.com"
    assert ovx.ovpnexportcountry == "US"


# ---------- Shellcmd --------------------------------------------------------


def test_shellcmd_structure():
    xml = """
    <pfsense>
      <installedpackages>
        <shellcmdsettings>
          <config>
            <cmd>/usr/local/bin/custom-boot.sh</cmd>
            <cmdtype>earlyshellcmd</cmdtype>
            <descr>Custom boot hook</descr>
          </config>
          <config>
            <cmd>/sbin/pfctl -F all</cmd>
            <cmdtype>afterfilterchangeshellcmd</cmdtype>
            <disabled>on</disabled>
          </config>
        </shellcmdsettings>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    pkgs = cfg.installedpackages
    assert pkgs is not None
    sc = pkgs.shellcmd
    assert sc is not None
    assert len(sc.entries) == 2
    first = sc.entries[0]
    assert first.cmd == "/usr/local/bin/custom-boot.sh"
    assert first.cmdtype == "earlyshellcmd"
    assert first.disabled is False
    assert sc.entries[1].disabled is True


# ---------- Metadata tags (menu, service, package) --------------------------


def test_metadata_tags_consumed_without_clutter():
    """``<menu>``, ``<service>``, ``<package>`` are webGUI / package
    metadata that carry no operational config. v0.17.0 claims them so
    they no longer pollute the "Other packages" fallback list.
    Include a real package (miniupnpd) so the ``InstalledPackages``
    object is produced — metadata alone would return ``None`` and
    there'd be nothing to inspect."""
    xml = """
    <pfsense>
      <installedpackages>
        <miniupnpd>
          <enable>on</enable>
        </miniupnpd>
        <menu><name>pfBlockerNG</name></menu>
        <service><name>pfb_dnsbl</name></service>
        <package><name>pfBlockerNG-devel</name></package>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    pkgs = cfg.installedpackages
    assert pkgs is not None
    unknown_tags = {u.tag for u in pkgs.unknown}
    for tag in ("menu", "service", "package"):
        assert tag not in unknown_tags, (
            f"{tag} leaked into 'Other packages'; should be metadata-ignored"
        )
