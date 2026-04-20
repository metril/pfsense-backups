"""Tests for v0.14.0 — sshdata, misc (lastchange/theme/diag/dhcpbackend/
bridge/proxyarp/ifgroups/ezshaper/ovpnserver), extra_vpn (l2tp/pppoes),
apikeys. Every parser that surfaces a credential field gets a secret
leak check — if the redaction wiring regresses, the raw secret will
show up in ``model_dump_json()`` and the corresponding assertion fires.
"""

from __future__ import annotations

import textwrap

from pfsense_shared.pfsense_parser import parse
from pfsense_shared.pfsense_redact import REDACTED


def _parse(xml: str):
    return parse(textwrap.dedent(xml).strip().encode())


def test_sshdata_modern_sshkeyfile_shape() -> None:
    """pfSense 2.5+ stores SSH host keys as <sshkeyfile> entries — each
    with <filename> + <xmldata>. Private halves (no ``.pub`` suffix)
    must redact; ``.pub`` halves stay visible so a key rotation still
    shows up in a diff."""
    cfg = _parse(
        """
        <pfsense>
          <sshdata>
            <sshkeyfile>
              <filename>ssh_host_rsa_key</filename>
              <xmldata>LEAKY_RSA_PRIVKEY_BLOB</xmldata>
            </sshkeyfile>
            <sshkeyfile>
              <filename>ssh_host_rsa_key.pub</filename>
              <xmldata>ssh-rsa AAAAB3... rsa-pub</xmldata>
            </sshkeyfile>
            <sshkeyfile>
              <filename>ssh_host_ed25519_key</filename>
              <xmldata>LEAKY_ED25519_PRIVKEY_BLOB</xmldata>
            </sshkeyfile>
            <sshkeyfile>
              <filename>ssh_host_ed25519_key.pub</filename>
              <xmldata>ssh-ed25519 AAAA... ed25519-pub</xmldata>
            </sshkeyfile>
          </sshdata>
        </pfsense>
        """
    )
    s = cfg.sshdata
    assert s is not None
    by_name = {k.filename: k for k in s.keys}
    assert by_name["ssh_host_rsa_key"].is_private
    assert by_name["ssh_host_rsa_key"].xmldata == REDACTED
    assert not by_name["ssh_host_rsa_key.pub"].is_private
    assert "rsa-pub" in (by_name["ssh_host_rsa_key.pub"].xmldata or "")
    assert by_name["ssh_host_ed25519_key"].xmldata == REDACTED
    assert "ed25519-pub" in (
        by_name["ssh_host_ed25519_key.pub"].xmldata or ""
    )
    blob = cfg.model_dump_json()
    assert "LEAKY_RSA_PRIVKEY_BLOB" not in blob
    assert "LEAKY_ED25519_PRIVKEY_BLOB" not in blob


def test_sshdata_legacy_per_algorithm_shape_still_parsed() -> None:
    """Pre-2.5 backups used per-algorithm elements directly under
    <sshdata>. Keep parsing them as a fallback so old backups still
    surface host-key rotations. Exercises all four algorithms so the
    redaction-tag derivation is covered end-to-end."""
    cfg = _parse(
        """
        <pfsense>
          <sshdata>
            <ssh_rsa_key>LEAKY_LEGACY_RSA_PRIVKEY</ssh_rsa_key>
            <ssh_rsa_key_pub>ssh-rsa LEGACY... rsa-pub</ssh_rsa_key_pub>
            <ssh_ecdsa_key>LEAKY_LEGACY_ECDSA_PRIVKEY</ssh_ecdsa_key>
            <ssh_ecdsa_key_pub>ecdsa-sha2-nistp256 LEGACY... ecdsa-pub</ssh_ecdsa_key_pub>
            <ssh_ed25519_key>LEAKY_LEGACY_ED25519_PRIVKEY</ssh_ed25519_key>
            <ssh_ed25519_key_pub>ssh-ed25519 LEGACY... ed25519-pub</ssh_ed25519_key_pub>
            <ssh_dsa_key>LEAKY_LEGACY_DSA_PRIVKEY</ssh_dsa_key>
            <ssh_dsa_key_pub>ssh-dss LEGACY... dsa-pub</ssh_dsa_key_pub>
          </sshdata>
        </pfsense>
        """
    )
    s = cfg.sshdata
    assert s is not None
    by_name = {k.filename: k for k in s.keys}
    for algo in ("rsa", "ecdsa", "ed25519", "dsa"):
        priv = by_name[f"ssh_host_{algo}_key"]
        pub = by_name[f"ssh_host_{algo}_key.pub"]
        assert priv.is_private
        assert priv.xmldata == REDACTED
        assert not pub.is_private
        assert f"{algo}-pub" in (pub.xmldata or "") or "pub" in (
            pub.xmldata or ""
        )
    blob = cfg.model_dump_json()
    for leak in (
        "LEAKY_LEGACY_RSA_PRIVKEY",
        "LEAKY_LEGACY_ECDSA_PRIVKEY",
        "LEAKY_LEGACY_ED25519_PRIVKEY",
        "LEAKY_LEGACY_DSA_PRIVKEY",
    ):
        assert leak not in blob


def test_sshdata_mixed_shape_dedupes_by_filename() -> None:
    """Migration-in-progress snapshots may carry both the modern
    ``<sshkeyfile>`` entries AND the legacy per-algorithm elements
    for the same algorithm. The parser must prefer the modern shape
    and not double-emit the same filename."""
    cfg = _parse(
        """
        <pfsense>
          <sshdata>
            <sshkeyfile>
              <filename>ssh_host_rsa_key</filename>
              <xmldata>MODERN_RSA_PRIVKEY</xmldata>
            </sshkeyfile>
            <sshkeyfile>
              <filename>ssh_host_rsa_key.pub</filename>
              <xmldata>ssh-rsa MODERN... rsa-pub</xmldata>
            </sshkeyfile>
            <ssh_rsa_key>OLD_RSA_PRIVKEY_IGNORED</ssh_rsa_key>
            <ssh_rsa_key_pub>ssh-rsa OLD... ignored</ssh_rsa_key_pub>
            <ssh_ed25519_key>OLD_ED25519_PRIVKEY_PROMOTED</ssh_ed25519_key>
          </sshdata>
        </pfsense>
        """
    )
    s = cfg.sshdata
    assert s is not None
    filenames = [k.filename for k in s.keys]
    # Each filename appears at most once — no duplicates from the
    # legacy fallback.
    assert len(filenames) == len(set(filenames))
    # Modern wins for rsa; legacy promotes ed25519 that the modern
    # block didn't supply.
    assert "ssh_host_rsa_key" in filenames
    assert "ssh_host_ed25519_key" in filenames
    blob = cfg.model_dump_json()
    # Modern private is redacted.
    assert "MODERN_RSA_PRIVKEY" not in blob
    # Legacy content ignored entirely when modern wins.
    assert "OLD_RSA_PRIVKEY_IGNORED" not in blob
    # Legacy private for a separate algo still redacts.
    assert "OLD_ED25519_PRIVKEY_PROMOTED" not in blob


def test_misc_tags_parsed_no_longer_in_unrecognized() -> None:
    cfg = _parse(
        """
        <pfsense>
          <lastchange>1747459200</lastchange>
          <theme>pfsense-dark</theme>
          <diag>
            <ipv6nat/>
            <showallpasswords/>
          </diag>
          <dhcpbackend>kea</dhcpbackend>
          <bridge>
            <enable/>
            <interfaces>lan,opt1</interfaces>
          </bridge>
          <proxyarp>
            <proxyarpnet>
              <interface>wan</interface>
              <network>203.0.113.10/32</network>
              <descr>web edge</descr>
            </proxyarpnet>
          </proxyarp>
          <ifgroups>
            <ifgroupentry>
              <ifname>DMZ</ifname>
              <members>opt1 opt2</members>
              <descr>DMZ zones</descr>
            </ifgroupentry>
          </ifgroups>
        </pfsense>
        """
    )
    assert cfg.lastchange and cfg.lastchange.time == "1747459200"
    assert cfg.theme and cfg.theme.name == "pfsense-dark"
    assert cfg.diag and cfg.diag.ipv6nat is True
    assert cfg.diag and cfg.diag.showallpasswords is True
    assert cfg.dhcp_backend and cfg.dhcp_backend.backend == "kea"
    assert cfg.legacy_bridge and cfg.legacy_bridge.enabled is True
    assert cfg.legacy_bridge and cfg.legacy_bridge.interfaces == ["lan", "opt1"]
    assert len(cfg.proxyarp) == 1
    assert cfg.proxyarp[0].interface == "wan"
    assert cfg.proxyarp[0].network == "203.0.113.10/32"
    assert len(cfg.interface_groups) == 1
    assert cfg.interface_groups[0].ifname == "DMZ"
    assert cfg.interface_groups[0].members == ["opt1", "opt2"]
    # None of these tags should remain in unrecognized_sections.
    remaining = {r.tag for r in cfg.unrecognized_sections}
    for tag in (
        "lastchange",
        "theme",
        "diag",
        "dhcpbackend",
        "bridge",
        "proxyarp",
        "ifgroups",
    ):
        assert tag not in remaining


def test_ovpnserver_wizard_redacts_partial_key_material() -> None:
    cfg = _parse(
        """
        <pfsense>
          <ovpnserver>
            <step>6</step>
            <description>road-warrior-prod</description>
            <cacrt>-----BEGIN CERTIFICATE-----
public-ca-material
-----END CERTIFICATE-----</cacrt>
            <cakey>LEAKY_OVPN_WIZARD_CAKEY</cakey>
            <crt>-----BEGIN CERTIFICATE-----
public-srv-material
-----END CERTIFICATE-----</crt>
            <key>LEAKY_OVPN_WIZARD_SRVKEY</key>
          </ovpnserver>
        </pfsense>
        """
    )
    w = cfg.ovpnserver_wizard
    assert w is not None
    assert w.description == "road-warrior-prod"
    assert "public-ca-material" in (w.cacrt or "")
    assert w.cakey == REDACTED
    assert "public-srv-material" in (w.crt or "")
    assert w.key == REDACTED
    blob = cfg.model_dump_json()
    assert "LEAKY_OVPN_WIZARD_CAKEY" not in blob
    assert "LEAKY_OVPN_WIZARD_SRVKEY" not in blob


def test_ezshaper_wizard_state_no_secrets() -> None:
    cfg = _parse(
        """
        <pfsense>
          <ezshaper>
            <step>3</step>
            <interface>wan</interface>
            <upload>500</upload>
            <download>1000</download>
            <step2>
              <queue>
                <name>voip</name>
                <bandwidth>50</bandwidth>
                <bandwidth_unit>Kb</bandwidth_unit>
              </queue>
            </step2>
          </ezshaper>
        </pfsense>
        """
    )
    e = cfg.ezshaper
    assert e is not None
    assert e.interface == "wan"
    assert e.upload == "500"
    assert len(e.queues) == 1
    assert e.queues[0].name == "voip"


def test_apikeys_redact_secret_keep_public_id() -> None:
    cfg = _parse(
        """
        <pfsense>
          <apikeys>
            <item>
              <username>svc-ansible</username>
              <descr>Ansible automation</descr>
              <apikey>PUBLIC_API_KEY_ID</apikey>
              <apisecret>LEAKY_API_SECRET</apisecret>
            </item>
          </apikeys>
        </pfsense>
        """
    )
    assert len(cfg.apikeys) == 1
    a = cfg.apikeys[0]
    assert a.username == "svc-ansible"
    assert a.apikey == "PUBLIC_API_KEY_ID"
    assert a.apisecret == REDACTED
    blob = cfg.model_dump_json()
    assert "LEAKY_API_SECRET" not in blob
    assert "PUBLIC_API_KEY_ID" in blob


def test_l2tp_redacts_user_passwords_and_radius_secret() -> None:
    cfg = _parse(
        """
        <pfsense>
          <l2tp>
            <mode>server</mode>
            <interface>wan</interface>
            <localip>10.8.0.1</localip>
            <remoteip>10.8.0.100</remoteip>
            <radius>
              <enable/>
              <server>10.0.0.5</server>
              <secret>LEAKY_L2TP_RADIUS_SECRET</secret>
            </radius>
            <user>
              <name>alice</name>
              <ip>10.8.0.10</ip>
              <password>LEAKY_L2TP_USER_PW</password>
            </user>
          </l2tp>
        </pfsense>
        """
    )
    assert cfg.l2tp is not None
    assert cfg.l2tp.radius_secret == REDACTED
    assert cfg.l2tp.users[0].password == REDACTED
    blob = cfg.model_dump_json()
    assert "LEAKY_L2TP_RADIUS_SECRET" not in blob
    assert "LEAKY_L2TP_USER_PW" not in blob


def test_pppoes_redact_flat_username_encoding_and_radius_secret() -> None:
    """Real pfSense stores PPPoE users as a single <username> element
    whose text is space-separated ``name:base64password[:ip]``
    tuples. Make sure we parse that format and redact every password
    including the RADIUS shared secret."""
    cfg = _parse(
        """
        <pfsense>
          <pppoes>
            <pppoe>
              <pppoeid>0</pppoeid>
              <mode>server</mode>
              <interface>opt1</interface>
              <localip>10.9.0.1</localip>
              <remoteip>10.9.0.10</remoteip>
              <descr>edge isp</descr>
              <radius>
                <enable/>
                <server>10.0.0.9</server>
                <secret>LEAKY_PPPOE_RADIUS_SECRET</secret>
              </radius>
              <username>alice:LEAKY_PPPOE_B64_PW_1:10.9.0.11 bob:LEAKY_PPPOE_B64_PW_2:</username>
            </pppoe>
          </pppoes>
        </pfsense>
        """
    )
    assert len(cfg.pppoe_servers) == 1
    p = cfg.pppoe_servers[0]
    assert p.key == "0"
    assert p.radius_enabled is True
    assert p.radius_server == "10.0.0.9"
    assert p.radius_secret == REDACTED
    assert [u.name for u in p.users] == ["alice", "bob"]
    assert p.users[0].ip == "10.9.0.11"
    assert p.users[1].ip is None
    assert all(u.password == REDACTED for u in p.users)
    blob = cfg.model_dump_json()
    assert "LEAKY_PPPOE_B64_PW_1" not in blob
    assert "LEAKY_PPPOE_B64_PW_2" not in blob
    assert "LEAKY_PPPOE_RADIUS_SECRET" not in blob


def test_pppoes_missing_pppoeid_falls_back_to_stable_key() -> None:
    """When ``<pppoeid>`` is absent, the diff key should be
    content-derived (interface + descr) rather than loop index, so a
    reordering can't produce false-positive diffs."""
    cfg = _parse(
        """
        <pfsense>
          <pppoes>
            <pppoe>
              <interface>opt1</interface>
              <descr>east</descr>
              <username>alice:LEAKY:</username>
            </pppoe>
            <pppoe>
              <interface>opt2</interface>
              <descr>west</descr>
              <username>bob:LEAKY:</username>
            </pppoe>
          </pppoes>
        </pfsense>
        """
    )
    keys = [p.key for p in cfg.pppoe_servers]
    assert keys == ["opt1|east", "opt2|west"]


def test_v014_new_tags_covered_by_known_set() -> None:
    """Regression — every tag parsed in v0.14.0 must be consumed.
    A failure here means the parsing is wired but the tag still
    surfaces in ``unrecognized_sections`` because ``_KNOWN`` forgot
    it."""
    cfg = _parse(
        """
        <pfsense>
          <sshdata><ssh_rsa_key></ssh_rsa_key></sshdata>
          <lastchange>1</lastchange>
          <theme>x</theme>
          <diag></diag>
          <dhcpbackend>kea</dhcpbackend>
          <bridge></bridge>
          <proxyarp></proxyarp>
          <ifgroups></ifgroups>
          <ezshaper></ezshaper>
          <ovpnserver></ovpnserver>
          <apikeys></apikeys>
          <l2tp></l2tp>
          <pppoes></pppoes>
        </pfsense>
        """
    )
    remaining = {r.tag for r in cfg.unrecognized_sections}
    for tag in (
        "sshdata",
        "lastchange",
        "theme",
        "diag",
        "dhcpbackend",
        "bridge",
        "proxyarp",
        "ifgroups",
        "ezshaper",
        "ovpnserver",
        "apikeys",
        "l2tp",
        "pppoes",
    ):
        assert tag not in remaining, f"tag <{tag}> still in unrecognized_sections"
