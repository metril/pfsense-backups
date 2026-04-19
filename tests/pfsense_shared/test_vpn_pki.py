"""Tests for v0.11.4 sections: OpenVPN (server / client / CSO), IPsec
(phase1, phase2, mobile PSKs), and PKI (CA + cert).

Redaction coverage is the headline contract here — a VPN backup that
leaks a TLS key or a cert private key into the structured JSON would
be strictly worse than the raw XML tab (which the UI already warns is
the escape hatch). The ``test_no_secret_values_anywhere`` test is the
load-bearing assertion.
"""

from __future__ import annotations

import textwrap

from pfsense_shared.pfsense_diff import diff_configs
from pfsense_shared.pfsense_parser import parse
from pfsense_shared.pfsense_redact import REDACTED


def _parse(xml: str):
    return parse(textwrap.dedent(xml).strip().encode())


VPN_XML = """
<pfsense>
  <openvpn>
    <openvpn-server>
      <vpnid>1</vpnid>
      <description>road-warrior</description>
      <mode>server_user</mode>
      <protocol>UDP4</protocol>
      <local_port>1194</local_port>
      <tunnel_network>10.0.8.0/24</tunnel_network>
      <caref>ca1</caref>
      <certref>cert1</certref>
      <authmode>corp-ldap,local</authmode>
      <tls>LEAKED_TLS_KEY_ABCDEF</tls>
    </openvpn-server>
    <openvpn-client>
      <vpnid>2</vpnid>
      <description>site-b</description>
      <mode>p2p_tls</mode>
      <server_addr>vpn.siteb.example</server_addr>
      <server_port>1194</server_port>
      <caref>ca2</caref>
      <certref>cert2</certref>
    </openvpn-client>
    <openvpn-csc>
      <common_name>alice</common_name>
      <description>alice laptop</description>
      <tunnel_network>10.0.8.100</tunnel_network>
      <server_list>1,3</server_list>
    </openvpn-csc>
  </openvpn>
  <ipsec>
    <phase1>
      <ikeid>1</ikeid>
      <iketype>ikev2</iketype>
      <interface>wan</interface>
      <remote-gateway>203.0.113.1</remote-gateway>
      <authentication_method>psk</authentication_method>
      <pre-shared-key>LEAKED_PHASE1_PSK</pre-shared-key>
      <descr>aws-tunnel</descr>
      <encryption>
        <item>
          <encryption-algorithm><name>aes</name><keylen>256</keylen></encryption-algorithm>
          <hash-algorithm>sha256</hash-algorithm>
          <dhgroup>14</dhgroup>
        </item>
      </encryption>
    </phase1>
    <phase2>
      <uniqid>p2a</uniqid>
      <ikeid>1</ikeid>
      <mode>tunnel</mode>
      <localid><type>network</type><address>10.0.0.0</address><netbits>24</netbits></localid>
      <remoteid><type>network</type><address>172.16.0.0</address><netbits>16</netbits></remoteid>
      <encryption>
        <item>
          <encryption-algorithm><name>aes</name><keylen>256</keylen></encryption-algorithm>
          <hash-algorithm>sha256</hash-algorithm>
        </item>
      </encryption>
    </phase2>
    <mobilekey>
      <ident>user@example</ident>
      <ident_type>user_fqdn</ident_type>
      <pre-shared-key>LEAKED_MOBILE_PSK</pre-shared-key>
    </mobilekey>
  </ipsec>
  <ca>
    <refid>ca1</refid>
    <descr>internal CA</descr>
    <crt>AAAA</crt>
    <prv>LEAKED_CA_PRIVATE_KEY</prv>
    <serial>1</serial>
  </ca>
  <cert>
    <refid>cert1</refid>
    <descr>server cert</descr>
    <caref>ca1</caref>
    <type>server</type>
    <crt>BBBB</crt>
    <prv>LEAKED_CERT_PRIVATE_KEY</prv>
  </cert>
</pfsense>
"""


def test_openvpn_server_client_csc_parse() -> None:
    cfg = _parse(VPN_XML)
    assert len(cfg.openvpn_servers) == 1
    s = cfg.openvpn_servers[0]
    assert s.mode == "server_user"
    assert s.tls == REDACTED
    assert s.authmode == ["corp-ldap", "local"]

    assert len(cfg.openvpn_clients) == 1
    c = cfg.openvpn_clients[0]
    assert c.server_addr == "vpn.siteb.example"

    assert len(cfg.openvpn_cscs) == 1
    csc = cfg.openvpn_cscs[0]
    assert csc.common_name == "alice"
    assert csc.server_list == ["1", "3"]


def test_ipsec_phase1_phase2_and_psks() -> None:
    cfg = _parse(VPN_XML)
    assert len(cfg.ipsec_phase1) == 1
    p1 = cfg.ipsec_phase1[0]
    assert p1.iketype == "ikev2"
    assert p1.remote_gateway == "203.0.113.1"
    assert p1.pre_shared_key == REDACTED
    assert p1.encryption_set == ["aes-256/sha256/dh14"]

    assert len(cfg.ipsec_phase2) == 1
    p2 = cfg.ipsec_phase2[0]
    assert p2.mode == "tunnel"
    assert p2.local_address == "10.0.0.0"
    assert p2.local_netbits == "24"
    assert p2.remote_address == "172.16.0.0"
    assert p2.encryption_set == ["aes-256/sha256"]

    assert len(cfg.ipsec_psks) == 1
    k = cfg.ipsec_psks[0]
    assert k.ident == "user@example"
    assert k.pre_shared_key == REDACTED


def test_pki_ca_and_cert_private_keys_redacted() -> None:
    cfg = _parse(VPN_XML)
    assert len(cfg.certificate_authorities) == 1
    ca = cfg.certificate_authorities[0]
    assert ca.refid == "ca1"
    assert ca.crt == "AAAA"
    assert ca.prv == REDACTED

    assert len(cfg.certificates) == 1
    cert = cfg.certificates[0]
    assert cert.refid == "cert1"
    assert cert.type == "server"
    assert cert.caref == "ca1"
    assert cert.crt == "BBBB"
    assert cert.prv == REDACTED


def test_no_vpn_pki_secret_values_anywhere() -> None:
    cfg = _parse(VPN_XML)
    blob = cfg.model_dump_json()
    for secret in (
        "LEAKED_TLS_KEY_ABCDEF",
        "LEAKED_PHASE1_PSK",
        "LEAKED_MOBILE_PSK",
        "LEAKED_CA_PRIVATE_KEY",
        "LEAKED_CERT_PRIVATE_KEY",
    ):
        assert secret not in blob, f"{secret!r} leaked into parsed output"


def test_vpn_pki_diff_detects_added_and_rotated() -> None:
    a = _parse(VPN_XML)
    # Swap the cert body to simulate a rotation, add a second OpenVPN client.
    b_xml = VPN_XML.replace("<crt>BBBB</crt>", "<crt>CCCC</crt>").replace(
        "<openvpn-client>",
        "<openvpn-client>\n  <vpnid>3</vpnid>\n  <description>site-c</description>"
        "\n  <mode>p2p_tls</mode>\n  <server_addr>vpn.sitec.example</server_addr>"
        "\n</openvpn-client>\n<openvpn-client>",
    )
    b = _parse(b_xml)
    d = diff_configs(a, b)
    # Rotated cert shows up as a modified entry with a crt change.
    assert len(d.certificates.modified) == 1
    changes = {c.field for c in d.certificates.modified[0].changes}
    assert "crt" in changes
    # Added client surfaces under added.
    assert len(d.openvpn_clients.added) == 1
    assert d.openvpn_clients.added[0]["description"] == "site-c"
