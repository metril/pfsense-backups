"""Tests for v0.42.0 — comprehensive parser-gap sweep.

Covers the gaps a user audit surfaced: WireGuard at top-level
(pfSense CE 2.7+ / Plus 23.x+ layout), DNS Resolver host override
``<aliases>``, firewall rule traffic-shaping wiring, NAT NPt rules,
interface IPv6 prefix delegation, IPsec mobile clients + VTI,
OpenVPN extras (push/custom options, auth_user_pass), IPsec phase1/
phase2 extras (DPD, lifetime, pfsgroup), gateway monitoring
thresholds, bridge STP parameters, user 2FA + SSH keys, DHCP
static-map + server extras.

Every secret-bearing addition gets a ``LEAKY_*`` redaction check.
"""

from __future__ import annotations

import textwrap

from pfsense_shared.pfsense_parser import parse
from pfsense_shared.pfsense_redact import REDACTED


def _parse(xml: str):
    return parse(textwrap.dedent(xml).strip().encode())


# ---------- WireGuard at top-level (pfSense CE 2.7+ / Plus 23.x+) -----------


WIREGUARD_TOPLEVEL_XML = """
<pfsense>
  <wireguard>
    <tunnels>
      <item>
        <name>tun_wg0</name>
        <descr>built-in wg</descr>
        <enabled>yes</enabled>
        <listenport>51821</listenport>
        <mtu>1420</mtu>
        <address>10.7.1.1/24</address>
        <publickey>TOPLEVEL_PUB</publickey>
        <privatekey>LEAKY_TOPLEVEL_PRIV</privatekey>
      </item>
    </tunnels>
    <peers>
      <item>
        <descr>remote-laptop</descr>
        <enabled>yes</enabled>
        <tun>tun_wg0</tun>
        <endpoint>198.51.100.9</endpoint>
        <port>51820</port>
        <persistentkeepalive>25</persistentkeepalive>
        <allowedips>10.7.1.2/32</allowedips>
        <publickey>TOPLEVEL_PEER_PUB</publickey>
        <presharedkey>LEAKY_TOPLEVEL_PSK</presharedkey>
      </item>
    </peers>
  </wireguard>
</pfsense>
"""


def test_wireguard_toplevel_folds_into_installedpackages():
    cfg = _parse(WIREGUARD_TOPLEVEL_XML)
    assert cfg.installedpackages is not None
    wg = cfg.installedpackages.wireguard
    assert wg is not None
    assert len(wg.tunnels) == 1
    assert wg.tunnels[0].name == "tun_wg0"
    assert wg.tunnels[0].public_key == "TOPLEVEL_PUB"
    assert wg.tunnels[0].private_key == REDACTED
    assert len(wg.peers) == 1
    assert wg.peers[0].public_key == "TOPLEVEL_PEER_PUB"
    assert wg.peers[0].preshared_key == REDACTED
    # The top-level <wireguard> must NOT fall into the unrecognized
    # bucket — that's the visible bug the user reported.
    assert all(s.tag != "wireguard" for s in cfg.unrecognized_sections)
    dumped = cfg.model_dump_json()
    assert "LEAKY_TOPLEVEL_PRIV" not in dumped
    assert "LEAKY_TOPLEVEL_PSK" not in dumped


def test_wireguard_toplevel_wins_when_both_layouts_present():
    """Mid-upgrade configs may have both legacy and modern layouts.
    Prefer the top-level block (current source of truth on the firewall)."""
    xml = """
    <pfsense>
      <wireguard>
        <tunnels>
          <item><name>top_wg0</name><enabled>yes</enabled></item>
        </tunnels>
      </wireguard>
      <installedpackages>
        <wireguard>
          <tunnels>
            <item><name>legacy_wg0</name><enabled>yes</enabled></item>
          </tunnels>
        </wireguard>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    assert cfg.installedpackages is not None
    wg = cfg.installedpackages.wireguard
    assert wg is not None
    assert [t.name for t in wg.tunnels] == ["top_wg0"]


def test_wireguard_toplevel_bare_tag_still_produces_config():
    cfg = _parse("<pfsense><wireguard/></pfsense>")
    assert cfg.installedpackages is not None
    assert cfg.installedpackages.wireguard is not None
    assert cfg.installedpackages.wireguard.tunnels == []
    assert cfg.installedpackages.wireguard.peers == []


# ---------- DNS Resolver host override aliases ------------------------------


DNS_ALIASES_XML = """
<pfsense>
  <unbound>
    <enable/>
    <hosts>
      <host>www</host>
      <domain>example.lan</domain>
      <ip>10.0.0.10</ip>
      <descr>main web host</descr>
      <aliases>
        <item>
          <host>blog</host>
          <domain>example.lan</domain>
          <description>alias for blog</description>
        </item>
        <item>
          <host>shop</host>
          <domain>example.lan</domain>
          <description/>
        </item>
      </aliases>
    </hosts>
    <hosts>
      <host>db</host>
      <domain>example.lan</domain>
      <ip>10.0.0.20</ip>
      <descr>database</descr>
    </hosts>
  </unbound>
</pfsense>
"""


def test_dns_host_override_aliases_are_parsed():
    cfg = _parse(DNS_ALIASES_XML)
    assert cfg.dns is not None
    assert len(cfg.dns.host_overrides) == 2
    web, db = cfg.dns.host_overrides
    assert web.host == "www"
    assert len(web.aliases) == 2
    assert web.aliases[0].host == "blog"
    assert web.aliases[0].domain == "example.lan"
    assert web.aliases[0].description == "alias for blog"
    assert web.aliases[1].host == "shop"
    # Host overrides without an <aliases> sub-element still parse fine.
    assert db.host == "db"
    assert db.aliases == []


def test_dns_host_override_aliases_work_for_dnsmasq_too():
    """The parser unifies unbound + dnsmasq into one host_overrides
    list; aliases must work in both branches."""
    xml = """
    <pfsense>
      <dnsmasq>
        <enable/>
        <hosts>
          <host>mail</host>
          <domain>example.lan</domain>
          <ip>10.0.0.30</ip>
          <aliases>
            <item><host>smtp</host><domain>example.lan</domain></item>
          </aliases>
        </hosts>
      </dnsmasq>
    </pfsense>
    """
    cfg = _parse(xml)
    assert cfg.dns is not None
    assert cfg.dns.dnsmasq_enabled is True
    assert len(cfg.dns.host_overrides) == 1
    assert cfg.dns.host_overrides[0].aliases[0].host == "smtp"


# ---------- Firewall rule traffic-shaping wiring + audit blocks -------------


FIREWALL_SHAPING_XML = """
<pfsense>
  <filter>
    <rule>
      <tracker>1700000001</tracker>
      <type>pass</type>
      <interface>lan</interface>
      <ipprotocol>inet</ipprotocol>
      <protocol>tcp</protocol>
      <source><any/></source>
      <destination><any/></destination>
      <descr>web with shaping</descr>
      <tag>WEB</tag>
      <dnpipe>1</dnpipe>
      <pdnpipe>2</pdnpipe>
      <defaultqueue>qWebDown</defaultqueue>
      <ackqueue>qAck</ackqueue>
      <max-mss>1452</max-mss>
      <direction>any</direction>
      <created>
        <time>1700000000</time>
        <username>admin@10.0.0.1</username>
        <description>initial</description>
      </created>
      <updated>
        <time>1701000000</time>
        <username>admin@10.0.0.1</username>
        <description>added shaping</description>
      </updated>
    </rule>
    <rule>
      <tracker>1700000002</tracker>
      <type>pass</type>
      <interface>lan</interface>
      <source><any/></source>
      <destination><any/></destination>
      <descr>plain rule, no shaping</descr>
    </rule>
  </filter>
</pfsense>
"""


def test_firewall_rule_traffic_shaping_fields_parsed():
    cfg = _parse(FIREWALL_SHAPING_XML)
    assert len(cfg.firewall_rules) == 2
    shaped, plain = cfg.firewall_rules
    assert shaped.tag == "WEB"
    assert shaped.dnpipe == "1"
    assert shaped.pdnpipe == "2"
    assert shaped.queuename == "qWebDown"
    assert shaped.ackqueue == "qAck"
    assert shaped.max_mss == "1452"
    assert shaped.direction == "any"
    assert shaped.created is not None
    assert shaped.created.time == "1700000000"
    assert shaped.created.username == "admin@10.0.0.1"
    assert shaped.created.description == "initial"
    assert shaped.updated is not None
    assert shaped.updated.description == "added shaping"
    # Rules without these fields don't get spurious empty values.
    assert plain.tag is None
    assert plain.dnpipe is None
    assert plain.created is None
    assert plain.updated is None


# ---------- NAT NPt (IPv6 Network Prefix Translation) -----------------------


NAT_NPT_XML = """
<pfsense>
  <nat>
    <npt>
      <interface>wan</interface>
      <source><address>fc00:1234::/64</address></source>
      <destination><address>2001:db8:1234::/64</address></destination>
      <descr>NPt for LAN out WAN</descr>
    </npt>
    <npt>
      <interface>opt1</interface>
      <src>fc00:5678::/56</src>
      <dst>2001:db8:5678::/56</dst>
      <disabled/>
    </npt>
  </nat>
</pfsense>
"""


def test_nat_npt_rules_parsed():
    cfg = _parse(NAT_NPT_XML)
    npts = [r for r in cfg.nat_rules if r.kind == "npt"]
    assert len(npts) == 2
    a, b = npts
    assert a.interface == "wan"
    assert a.source.address == "fc00:1234::/64"
    assert a.destination.address == "2001:db8:1234::/64"
    assert a.descr == "NPt for LAN out WAN"
    assert a.disabled is False
    # Legacy <src>/<dst> form (without nested <address>).
    assert b.interface == "opt1"
    assert b.source.address == "fc00:5678::/56"
    assert b.destination.address == "2001:db8:5678::/56"
    assert b.disabled is True


# ---------- Interface IPv6 prefix delegation --------------------------------


IPV6_PD_XML = """
<pfsense>
  <interfaces>
    <wan>
      <if>em0</if>
      <enable/>
      <ipaddrv6>dhcp6</ipaddrv6>
      <dhcp6-ia-pd-len>60</dhcp6-ia-pd-len>
    </wan>
    <lan>
      <if>em1</if>
      <enable/>
      <ipaddrv6>track6</ipaddrv6>
      <track6-interface>wan</track6-interface>
      <track6-prefix-id>0</track6-prefix-id>
    </lan>
    <opt1>
      <if>em2</if>
      <enable/>
      <ipaddrv6>track6</ipaddrv6>
      <track6-interface>wan</track6-interface>
      <track6-prefix-id>1</track6-prefix-id>
    </opt1>
  </interfaces>
</pfsense>
"""


def test_interface_ipv6_prefix_delegation_fields_parsed():
    cfg = _parse(IPV6_PD_XML)
    by_key = {i.key: i for i in cfg.interfaces}
    wan, lan, opt1 = by_key["wan"], by_key["lan"], by_key["opt1"]
    assert wan.ipaddrv6 == "dhcp6"
    assert wan.dhcp6_ia_pd_len == "60"
    assert lan.ipaddrv6 == "track6"
    assert lan.track6_interface == "wan"
    assert lan.track6_prefix_id == "0"
    assert opt1.track6_prefix_id == "1"


# ---------- IPsec mobile clients, VTI, phase1/phase2 extras -----------------


IPSEC_RICH_XML = """
<pfsense>
  <ipsec>
    <phase1>
      <ikeid>1</ikeid>
      <iketype>ikev2</iketype>
      <interface>wan</interface>
      <remote-gateway>203.0.113.4</remote-gateway>
      <protocol>inet</protocol>
      <descr>main-site</descr>
      <authentication_method>pre_shared_key</authentication_method>
      <mode>main</mode>
      <nat_traversal>on</nat_traversal>
      <mobike>on</mobike>
      <dpd_action>restart</dpd_action>
      <dpd_delay>10</dpd_delay>
      <dpd_maxfail>5</dpd_maxfail>
      <lifetime>28800</lifetime>
      <reauth_time>0</reauth_time>
      <gw_duplicates/>
      <pre-shared-key>LEAKY_PSK1</pre-shared-key>
    </phase1>
    <phase2>
      <uniqid>p2a</uniqid>
      <ikeid>1</ikeid>
      <descr>vti tunnel</descr>
      <mode>vti</mode>
      <protocol>esp</protocol>
      <lifetime>3600</lifetime>
      <pinghost>10.9.9.2</pinghost>
      <pfsgroup>14</pfsgroup>
      <mode_vti_addr>10.9.9.1/30</mode_vti_addr>
      <mode_vti_remote_addr>10.9.9.2</mode_vti_remote_addr>
    </phase2>
    <mobileclients>
      <enable/>
      <user_source>system</user_source>
      <group_source>system</group_source>
      <pool_address>10.20.0.0</pool_address>
      <pool_netbits>24</pool_netbits>
      <dns_address>10.0.0.1</dns_address>
      <login_banner>Welcome</login_banner>
    </mobileclients>
  </ipsec>
</pfsense>
"""


def test_ipsec_phase1_extras_parsed():
    cfg = _parse(IPSEC_RICH_XML)
    assert len(cfg.ipsec_phase1) == 1
    p1 = cfg.ipsec_phase1[0]
    assert p1.mode == "main"
    assert p1.nat_traversal == "on"
    assert p1.mobike == "on"
    assert p1.dpd_action == "restart"
    assert p1.dpd_delay == "10"
    assert p1.dpd_maxfail == "5"
    assert p1.lifetime == "28800"
    assert p1.gw_duplicates is True
    assert p1.pre_shared_key == REDACTED
    assert "LEAKY_PSK1" not in cfg.model_dump_json()


def test_ipsec_phase2_vti_and_extras_parsed():
    cfg = _parse(IPSEC_RICH_XML)
    assert len(cfg.ipsec_phase2) == 1
    p2 = cfg.ipsec_phase2[0]
    assert p2.mode == "vti"
    assert p2.lifetime == "3600"
    assert p2.keepalive == "10.9.9.2"
    assert p2.pfsgroup == "14"
    assert p2.mode_vti_addr == "10.9.9.1/30"
    assert p2.mode_vti_remote_addr == "10.9.9.2"


def test_ipsec_mobile_clients_parsed():
    cfg = _parse(IPSEC_RICH_XML)
    assert cfg.ipsec_mobile_clients is not None
    mob = cfg.ipsec_mobile_clients
    assert mob.enable is True
    assert mob.user_source == "system"
    assert mob.pool_address == "10.20.0.0"
    assert mob.pool_netbits == "24"
    assert mob.dns_address == "10.0.0.1"
    assert mob.login_banner == "Welcome"


# ---------- OpenVPN server/client extras (3.1) ------------------------------


OPENVPN_RICH_XML = """
<pfsense>
  <openvpn>
    <openvpn-server>
      <vpnid>1</vpnid>
      <description>roadwarrior</description>
      <mode>server_user</mode>
      <protocol>UDP4</protocol>
      <interface>wan</interface>
      <local_port>1194</local_port>
      <tunnel_network>10.10.0.0/24</tunnel_network>
      <crypto>AES-256-GCM</crypto>
      <push_options>push "redirect-gateway def1"</push_options>
      <custom_options>tls-version-min 1.2</custom_options>
      <compression>adaptive</compression>
      <verify_x509_name>servercert</verify_x509_name>
      <data_ciphers>AES-256-GCM:AES-128-GCM</data_ciphers>
      <data_ciphers_fallback>AES-256-GCM</data_ciphers_fallback>
      <fragment>1300</fragment>
      <tunnel_mtu>1400</tunnel_mtu>
      <tls>LEAKY_TLS_KEY</tls>
    </openvpn-server>
    <openvpn-client>
      <vpnid>2</vpnid>
      <description>outbound to provider</description>
      <mode>p2p_tls</mode>
      <interface>wan</interface>
      <server_addr>vpn.example.com</server_addr>
      <server_port>1194</server_port>
      <auth_user>vpn_user</auth_user>
      <auth_pass>LEAKY_AUTH_PASS</auth_pass>
      <auth_user_pass>LEAKY_AUTH_BLOB</auth_user_pass>
      <custom_options>auth-nocache</custom_options>
    </openvpn-client>
  </openvpn>
</pfsense>
"""


def test_openvpn_server_extras_parsed():
    cfg = _parse(OPENVPN_RICH_XML)
    assert len(cfg.openvpn_servers) == 1
    s = cfg.openvpn_servers[0]
    assert s.push_options == 'push "redirect-gateway def1"'
    assert s.custom_options == "tls-version-min 1.2"
    assert s.comp_lzo == "adaptive"
    assert s.verify_x509_name == "servercert"
    assert s.data_ciphers == "AES-256-GCM:AES-128-GCM"
    assert s.fragment == "1300"
    assert s.tunnel_mtu == "1400"
    assert s.tls == REDACTED
    assert "LEAKY_TLS_KEY" not in cfg.model_dump_json()


def test_openvpn_client_credentials_redacted():
    cfg = _parse(OPENVPN_RICH_XML)
    assert len(cfg.openvpn_clients) == 1
    c = cfg.openvpn_clients[0]
    assert c.username == "vpn_user"  # username is identity, not secret
    assert c.password == REDACTED
    assert c.auth_user_pass == REDACTED
    assert c.custom_options == "auth-nocache"
    dumped = cfg.model_dump_json()
    assert "LEAKY_AUTH_PASS" not in dumped
    assert "LEAKY_AUTH_BLOB" not in dumped
    assert "vpn_user" in dumped  # identity stays


# ---------- Gateway monitoring thresholds (3.3) -----------------------------


GATEWAY_THRESHOLDS_XML = """
<pfsense>
  <gateways>
    <gateway_item>
      <name>WAN_DHCP</name>
      <interface>wan</interface>
      <gateway>dynamic</gateway>
      <ipprotocol>inet</ipprotocol>
      <monitor>8.8.8.8</monitor>
      <weight>1</weight>
      <defaultgw/>
      <latencylow>200</latencylow>
      <latencyhigh>500</latencyhigh>
      <losslow>10</losslow>
      <losshigh>20</losshigh>
      <interval>500</interval>
      <time_period>60000</time_period>
      <alert_interval>1000</alert_interval>
      <loss_interval>2000</loss_interval>
      <data_payload>1</data_payload>
      <force_down/>
    </gateway_item>
  </gateways>
</pfsense>
"""


def test_gateway_monitoring_thresholds_parsed():
    cfg = _parse(GATEWAY_THRESHOLDS_XML)
    assert len(cfg.gateways) == 1
    g = cfg.gateways[0]
    assert g.name == "WAN_DHCP"
    assert g.latencylow == "200"
    assert g.latencyhigh == "500"
    assert g.losslow == "10"
    assert g.losshigh == "20"
    assert g.interval == "500"
    assert g.time_period == "60000"
    assert g.alert_interval == "1000"
    assert g.loss_interval == "2000"
    assert g.data_payload == "1"
    assert g.force_down is True


# ---------- Bridge STP parameters (3.4) -------------------------------------


BRIDGE_STP_XML = """
<pfsense>
  <bridges>
    <bridged>
      <bridgeif>bridge0</bridgeif>
      <members>em0,em1,em2</members>
      <descr>core bridge</descr>
      <enablestp/>
      <proto>rstp</proto>
      <priority>4096</priority>
      <fwdelay>15</fwdelay>
      <hellotime>2</hellotime>
      <maxage>20</maxage>
      <holdcnt>6</holdcnt>
      <ifpriority>em0,16,em1,32,em2,48</ifpriority>
      <ifpathcost>em0,2000,em1,4000</ifpathcost>
    </bridged>
  </bridges>
</pfsense>
"""


def test_bridge_stp_parameters_parsed():
    cfg = _parse(BRIDGE_STP_XML)
    assert len(cfg.bridges) == 1
    b = cfg.bridges[0]
    assert b.enablestp is True
    assert b.stp_proto == "rstp"
    assert b.stp_priority == "4096"
    assert b.stp_forward_delay == "15"
    assert b.stp_hello_time == "2"
    assert b.stp_maxage == "20"
    assert b.stp_holdcnt == "6"
    assert b.stp_member_priorities == {"em0": "16", "em1": "32", "em2": "48"}
    assert b.stp_member_pathcosts == {"em0": "2000", "em1": "4000"}


# ---------- User 2FA + SSH keys (3.5) ---------------------------------------


USER_2FA_XML = """
<pfsense>
  <system>
    <user>
      <name>alice</name>
      <uid>2000</uid>
      <scope>user</scope>
      <bcrypt-hash>LEAKY_BCRYPT</bcrypt-hash>
      <otp_seed>LEAKY_OTP_SEED</otp_seed>
      <u2f_keys>
        <item>
          <keyHandle>handle-1-abcdef</keyHandle>
        </item>
        <item>
          <keyHandle>handle-2-uvwxyz</keyHandle>
        </item>
      </u2f_keys>
      <authorizedkeys>ssh-ed25519 AAAA... alice@laptop</authorizedkeys>
    </user>
  </system>
</pfsense>
"""


def test_user_2fa_and_ssh_key_parsed_and_redacted():
    cfg = _parse(USER_2FA_XML)
    assert len(cfg.users) == 1
    u = cfg.users[0]
    assert u.name == "alice"
    assert u.bcrypt_hash == REDACTED
    assert u.otp_seed == REDACTED
    assert u.u2f_keys == ["handle-1-abcdef", "handle-2-uvwxyz"]
    assert u.ssh_key == "ssh-ed25519 AAAA... alice@laptop"
    dumped = cfg.model_dump_json()
    assert "LEAKY_BCRYPT" not in dumped
    assert "LEAKY_OTP_SEED" not in dumped
    # SSH key is identity, not a secret — survives.
    assert "alice@laptop" in dumped


# ---------- DHCP static-map + server extras (3.6) ---------------------------


DHCP_RICH_XML = """
<pfsense>
  <dhcpd>
    <lan>
      <enable/>
      <range><from>10.0.0.50</from><to>10.0.0.250</to></range>
      <domain>example.lan</domain>
      <dnsserver>10.0.0.1</dnsserver>
      <gateway>10.0.0.1</gateway>
      <ddnsdomain>example.lan</ddnsdomain>
      <ddnsdomainprimary>10.0.0.2</ddnsdomainprimary>
      <ddnsdomainkey>LEAKY_TSIG_KEY</ddnsdomainkey>
      <defaultleasetime>7200</defaultleasetime>
      <maxleasetime>86400</maxleasetime>
      <numberoptions>
        <item>
          <number>252</number>
          <value>http://wpad.example.lan/wpad.dat</value>
          <type>text</type>
        </item>
        <item>
          <number>119</number>
          <value>example.lan</value>
        </item>
      </numberoptions>
      <staticmap>
        <mac>aa:bb:cc:dd:ee:ff</mac>
        <ipaddr>10.0.0.10</ipaddr>
        <hostname>printer</hostname>
        <descr>color printer</descr>
        <ddnsdomain>print.example.lan</ddnsdomain>
        <filename>pxelinux.0</filename>
        <rootpath>/srv/nfs</rootpath>
        <gateway>10.0.0.2</gateway>
        <dnsserver>10.0.0.3</dnsserver>
      </staticmap>
    </lan>
  </dhcpd>
</pfsense>
"""


def test_dhcp_server_and_static_map_extras_parsed():
    cfg = _parse(DHCP_RICH_XML)
    assert len(cfg.dhcp_servers) == 1
    s = cfg.dhcp_servers[0]
    assert s.ddnsdomain == "example.lan"
    assert s.ddnsdomainprimary == "10.0.0.2"
    assert s.ddnsdomainkey == REDACTED
    assert s.defaultleasetime == "7200"
    assert s.maxleasetime == "86400"
    assert len(s.numberoptions) == 2
    assert s.numberoptions[0].number == "252"
    assert s.numberoptions[0].value == "http://wpad.example.lan/wpad.dat"
    assert s.numberoptions[0].type == "text"
    assert s.numberoptions[1].number == "119"
    assert len(s.static_mappings) == 1
    m = s.static_mappings[0]
    assert m.ddnsdomain == "print.example.lan"
    assert m.filename == "pxelinux.0"
    assert m.rootpath == "/srv/nfs"
    assert m.gateway == "10.0.0.2"
    assert m.dnsservers == ["10.0.0.3"]
    assert "LEAKY_TSIG_KEY" not in cfg.model_dump_json()
