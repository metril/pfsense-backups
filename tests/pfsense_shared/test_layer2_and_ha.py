"""Tests for v0.11.1 sections: VLANs, bridges, GIF/GRE, PPP, QinQ, WOL,
virtual IPs (CARP/IP-alias/proxy-ARP), and HA sync.
"""

from __future__ import annotations

import textwrap

from pfsense_shared.pfsense_diff import diff_configs
from pfsense_shared.pfsense_parser import parse
from pfsense_shared.pfsense_redact import REDACTED


def _parse(xml: str):
    return parse(textwrap.dedent(xml).strip().encode())


def test_vlans_and_bridges() -> None:
    cfg = _parse("""
        <pfsense>
          <vlans>
            <vlan><if>em0</if><tag>100</tag><vlanif>em0.100</vlanif><descr>mgmt</descr></vlan>
            <vlan><if>em0</if><tag>200</tag><vlanif>em0.200</vlanif><pcp>5</pcp></vlan>
          </vlans>
          <bridges>
            <bridged>
              <bridgeif>bridge0</bridgeif>
              <members>em1,em2</members>
              <descr>lab</descr>
              <enablestp/>
            </bridged>
          </bridges>
        </pfsense>
    """)
    assert [v.key for v in cfg.vlans] == ["em0.100", "em0.200"]
    assert cfg.vlans[1].pcp == "5"
    assert cfg.bridges[0].bridgeif == "bridge0"
    assert cfg.bridges[0].members == ["em1", "em2"]
    assert cfg.bridges[0].enablestp is True


def test_gif_and_gre_tunnels() -> None:
    cfg = _parse("""
        <pfsense>
          <gifs>
            <gif>
              <gifif>gif0</gifif>
              <if>wan</if>
              <remote-addr>198.51.100.1</remote-addr>
              <tunnel-remote-addr>10.0.0.2</tunnel-remote-addr>
            </gif>
          </gifs>
          <gres>
            <gre>
              <greif>gre0</greif>
              <if>wan</if>
              <remote-addr>198.51.100.2</remote-addr>
            </gre>
          </gres>
        </pfsense>
    """)
    assert len(cfg.gifs) == 1
    assert cfg.gifs[0].kind == "gif"
    assert cfg.gifs[0].name == "gif0"
    assert cfg.gifs[0].remote_addr == "198.51.100.1"
    assert len(cfg.gres) == 1
    assert cfg.gres[0].kind == "gre"


def test_ppp_and_qinq_and_wol() -> None:
    cfg = _parse("""
        <pfsense>
          <ppps>
            <ppp>
              <ptpid>0</ptpid>
              <type>pppoe</type>
              <if>em3</if>
              <username>isp_user</username>
              <password>leaked_isp_password</password>
            </ppp>
          </ppps>
          <qinqs>
            <qinqentry>
              <if>em0</if>
              <tag>100</tag>
              <members>10 20 30</members>
              <descr>provider-vlan</descr>
            </qinqentry>
          </qinqs>
          <wol>
            <wolentry>
              <mac>aa:bb:cc:dd:ee:ff</mac>
              <interface>lan</interface>
              <descr>workstation</descr>
            </wolentry>
          </wol>
        </pfsense>
    """)
    assert cfg.ppps[0].type == "pppoe"
    assert cfg.ppps[0].username == "isp_user"
    # PPP password leakage check: redaction is applied at the
    # secret-scan level (see test_no_secret_values_anywhere_in_parsed_output).
    dump = cfg.model_dump_json()
    assert "leaked_isp_password" not in dump

    assert cfg.qinqs[0].key == "em0.100"
    assert cfg.qinqs[0].members == ["10", "20", "30"]

    assert cfg.wol[0].mac == "aa:bb:cc:dd:ee:ff"


def test_virtual_ips_with_carp_password_redacted() -> None:
    cfg = _parse("""
        <pfsense>
          <virtualip>
            <vip>
              <uniqid>v1</uniqid>
              <mode>carp</mode>
              <interface>lan</interface>
              <subnet>192.168.1.1</subnet>
              <subnet_bits>24</subnet_bits>
              <vhid>1</vhid>
              <advbase>1</advbase>
              <advskew>0</advskew>
              <password>carp_cluster_secret</password>
              <descr>lan-vip</descr>
            </vip>
          </virtualip>
        </pfsense>
    """)
    assert len(cfg.virtual_ips) == 1
    v = cfg.virtual_ips[0]
    assert v.key == "v1"
    assert v.mode == "carp"
    assert v.vhid == "1"
    assert v.password == REDACTED
    # Leak check
    assert "carp_cluster_secret" not in cfg.model_dump_json()


def test_hasync_is_optional_and_password_redacted() -> None:
    cfg = _parse("""
        <pfsense>
          <hasync>
            <pfsyncenabled>on</pfsyncenabled>
            <pfsyncinterface>sync</pfsyncinterface>
            <pfsyncpeerip>10.200.0.2</pfsyncpeerip>
            <synchronizetoip>10.200.0.2</synchronizetoip>
            <username>sync</username>
            <password>xmlrpc_sync_password</password>
            <synchronizerules/>
            <synchronizenat/>
            <synchronizealiases/>
            <synchronizecerts/>
          </hasync>
        </pfsense>
    """)
    assert cfg.hasync is not None
    h = cfg.hasync
    assert h.pfsyncenabled is True
    assert h.pfsyncinterface == "sync"
    assert h.password == REDACTED
    assert h.synchronizerules is True
    assert h.synchronizenat is True
    assert h.synchronizealiases is True
    assert h.synchronizecerts is True
    assert h.synchronizedhcpd is False
    assert "xmlrpc_sync_password" not in cfg.model_dump_json()


def test_diff_on_v0_11_1_sections() -> None:
    a = _parse("""
        <pfsense>
          <vlans>
            <vlan><if>em0</if><tag>100</tag><vlanif>em0.100</vlanif><descr>mgmt</descr></vlan>
          </vlans>
          <virtualip>
            <vip><uniqid>v1</uniqid><mode>carp</mode><subnet>192.168.1.1</subnet><vhid>1</vhid></vip>
          </virtualip>
        </pfsense>
    """)
    b = _parse("""
        <pfsense>
          <vlans>
            <vlan><if>em0</if><tag>100</tag><vlanif>em0.100</vlanif><descr>management</descr></vlan>
            <vlan><if>em0</if><tag>200</tag><vlanif>em0.200</vlanif></vlan>
          </vlans>
          <virtualip>
            <vip><uniqid>v1</uniqid><mode>carp</mode><subnet>192.168.1.2</subnet><vhid>1</vhid></vip>
          </virtualip>
        </pfsense>
    """)
    d = diff_configs(a, b)
    # VLAN added + one modified
    assert len(d.vlans.added) == 1
    assert d.vlans.added[0]["key"] == "em0.200"
    assert len(d.vlans.modified) == 1
    assert d.vlans.modified[0].key == "em0.100"
    # CARP subnet changed
    assert len(d.virtual_ips.modified) == 1
    subnet_changes = [
        c for c in d.virtual_ips.modified[0].changes if c.field == "subnet"
    ]
    assert len(subnet_changes) == 1
    assert subnet_changes[0].before == "192.168.1.1"
    assert subnet_changes[0].after == "192.168.1.2"


def test_hasync_added_appears_in_diff() -> None:
    a = _parse("<pfsense></pfsense>")
    b = _parse(
        "<pfsense><hasync><pfsyncenabled>on</pfsyncenabled>"
        "<pfsyncinterface>sync</pfsyncinterface></hasync></pfsense>"
    )
    d = diff_configs(a, b)
    assert len(d.hasync.added) == 1
    assert d.hasync.added[0]["pfsyncenabled"] is True
