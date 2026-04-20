"""Tests for v0.16.0 — pfBlockerNG / FRR / Squid sub-tag consumption
plus v0.16.1 follow-ups (credential redaction + orphan CONSUMED_TAGS).

These packages emit extra sibling tags under ``<installedpackages>``
whose presence indicates a feature is configured (pfBlockerNG
categories, FRR IPv6 OSPF daemon, Squid auth/cache/antivirus/remote).
Before v0.16.0 those tags leaked into the viewer's "Other packages
(raw XML)" panel. This module asserts:

1. Each sub-tag is consumed by its parent parser — no leakage into
   ``installedpackages.unknown``.
2. The matching presence boolean on the parent config flips to
   ``True`` when the sub-tag is present.
3. A fresh per-package smoke: parsing the sub-tag ALONE (without
   the parent's root tag) still produces a structured config
   object instead of dropping it.
4. Credentials inside a consumed sub-tag (``ldap_pass`` /
   ``radius_secret`` in ``<squidauth>``, oinkcode-embedded URLs in
   pfBlockerNG Reputation/Blacklist tabs, OSPFv3 MD5 keys in
   ``<frrospfdinterfaces>``) are structured AND redacted, not
   silently dropped. v0.16.1 security pass.
"""

from __future__ import annotations

import textwrap

from pfsense_shared.pfsense_parser import parse
from pfsense_shared.pfsense_redact import REDACTED


def _parse(xml: str):
    return parse(textwrap.dedent(xml).strip().encode())


# ---------- pfBlockerNG sub-tags -------------------------------------------


PFBLOCKERNG_SUBPACKAGES_XML = """
<pfsense>
  <installedpackages>
    <pfblockerng>
      <enable_cb>on</enable_cb>
    </pfblockerng>
    <pfblockerngtopspammers>
      <enable_cb>on</enable_cb>
    </pfblockerngtopspammers>
    <pfblockerngblacklist/>
    <pfblockerngsafesearch/>
    <pfblockerngreputation/>
  </installedpackages>
</pfsense>
"""


def test_pfblockerng_subtags_consumed_and_flagged():
    cfg = _parse(PFBLOCKERNG_SUBPACKAGES_XML)
    pkgs = cfg.installedpackages
    assert pkgs is not None
    unknown_tags = {u.tag for u in pkgs.unknown}
    for tag in (
        "pfblockerngtopspammers",
        "pfblockerngblacklist",
        "pfblockerngsafesearch",
        "pfblockerngreputation",
    ):
        assert tag not in unknown_tags, (
            f"{tag} leaked into 'Other packages' (should be consumed)"
        )
    pbn = pkgs.pfblockerng
    assert pbn is not None
    assert pbn.topspammers_present is True
    assert pbn.blacklist_present is True
    assert pbn.safesearch_present is True
    assert pbn.reputation_present is True


def test_pfblockerng_subtags_alone_still_produce_config():
    xml = """
    <pfsense>
      <installedpackages>
        <pfblockerngtopspammers/>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    pkgs = cfg.installedpackages
    assert pkgs is not None
    assert pkgs.pfblockerng is not None
    assert pkgs.pfblockerng.topspammers_present is True


# ---------- FRR sub-tags ----------------------------------------------------


FRR_SUBPACKAGES_XML = """
<pfsense>
  <installedpackages>
    <frr>
      <enable>on</enable>
    </frr>
    <frrospfd/>
    <frrospfdareas/>
    <frrospfdinterfaces/>
    <frrglobalacls/>
    <frrglobalprefixes/>
  </installedpackages>
</pfsense>
"""


def test_frr_subtags_consumed_and_flagged():
    cfg = _parse(FRR_SUBPACKAGES_XML)
    pkgs = cfg.installedpackages
    assert pkgs is not None
    unknown_tags = {u.tag for u in pkgs.unknown}
    for tag in (
        "frrospfd",
        "frrospfdareas",
        "frrospfdinterfaces",
        "frrglobalacls",
        "frrglobalprefixes",
    ):
        assert tag not in unknown_tags
    frr = pkgs.frr
    assert frr is not None
    assert frr.ospfd_present is True
    assert frr.ospfd_areas_present is True
    assert frr.ospfd_interfaces_present is True
    assert frr.global_acls_present is True
    assert frr.global_prefixes_present is True


def test_frr_subtags_alone_still_produce_config():
    xml = """
    <pfsense>
      <installedpackages>
        <frrospfd/>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    pkgs = cfg.installedpackages
    assert pkgs is not None
    assert pkgs.frr is not None
    assert pkgs.frr.ospfd_present is True


# ---------- Squid sub-tags --------------------------------------------------


SQUID_SUBPACKAGES_XML = """
<pfsense>
  <installedpackages>
    <squid>
      <enable>on</enable>
    </squid>
    <squidcache/>
    <squidremote/>
    <squidauth/>
    <squidantivirus/>
  </installedpackages>
</pfsense>
"""


def test_squid_subtags_consumed_and_flagged():
    cfg = _parse(SQUID_SUBPACKAGES_XML)
    pkgs = cfg.installedpackages
    assert pkgs is not None
    unknown_tags = {u.tag for u in pkgs.unknown}
    for tag in ("squidcache", "squidremote", "squidauth", "squidantivirus"):
        assert tag not in unknown_tags
    sq = pkgs.squid
    assert sq is not None
    assert sq.cache_present is True
    assert sq.remote_present is True
    # auth is now structured (v0.16.1). A bare ``<squidauth/>`` with
    # no inner fields still produces a SquidAuthConfig with all-None
    # members — the Bundle's "auth is not None" signals presence.
    assert sq.auth is not None
    assert sq.antivirus_present is True


# ---------- v0.16.1 security follow-ups -------------------------------------


def test_squidauth_structures_and_redacts_credentials():
    """v0.16.0 swallowed <squidauth> wholesale. v0.16.1 structures the
    LDAP bind password + RADIUS shared secret and routes both through
    the redaction engine."""
    xml = """
    <pfsense>
      <installedpackages>
        <squidauth>
          <item>
            <auth_method>ldap</auth_method>
            <ldap_server>ldap.example.com</ldap_server>
            <ldap_user>cn=squid,dc=example,dc=com</ldap_user>
            <ldap_pass>LEAKY_LDAP_PASSWORD</ldap_pass>
            <radius_server>radius.example.com</radius_server>
            <radius_secret>LEAKY_RADIUS_SECRET</radius_secret>
          </item>
        </squidauth>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    pkgs = cfg.installedpackages
    assert pkgs is not None
    auth = pkgs.squid.auth if pkgs.squid else None
    assert auth is not None
    # Structured fields survive:
    assert auth.auth_method == "ldap"
    assert auth.ldap_server == "ldap.example.com"
    assert auth.ldap_binddn == "cn=squid,dc=example,dc=com"
    assert auth.radius_server == "radius.example.com"
    # Credentials redacted, plaintext never leaks anywhere in the tree.
    assert auth.ldap_pass == REDACTED
    assert auth.radius_secret == REDACTED
    dumped = cfg.model_dump_json()
    assert "LEAKY_LDAP_PASSWORD" not in dumped
    assert "LEAKY_RADIUS_SECRET" not in dumped


def test_pfblockerng_reputation_and_blacklist_urls_are_scrubbed():
    """Subscriber oinkcode in feed URLs under
    <pfblockerngreputation> / <pfblockerngblacklist> must be scrubbed
    by ``_scrub_feed_url`` — same path the v4/v6/DNSBL feeds already
    use."""
    xml = """
    <pfsense>
      <installedpackages>
        <pfblockerngreputation>
          <config>
            <aliasname>ET_Pro_Rep</aliasname>
            <action>Alias Deny</action>
            <row>
              <state>Enabled</state>
              <url>https://rules.emergingthreats.net/1234567890abcdef1234567890abcdef12345678/suricata/reputation.rules</url>
              <format>auto</format>
            </row>
          </config>
        </pfblockerngreputation>
        <pfblockerngblacklist>
          <config>
            <aliasname>Custom_BL</aliasname>
            <action>Unbound</action>
            <row>
              <state>Enabled</state>
              <url>https://feeds.example/blacklist.txt?oinkcode=LEAKY_BL_OINK</url>
              <format>auto</format>
            </row>
          </config>
        </pfblockerngblacklist>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    pkgs = cfg.installedpackages
    assert pkgs is not None
    pbn = pkgs.pfblockerng
    assert pbn is not None
    # Both feeds surfaced as structured rows, not as opaque presence
    # flags alone.
    headers = {f.header for f in pbn.feeds}
    assert "ET_Pro_Rep" in headers
    assert "Custom_BL" in headers
    # Path-embedded oinkcode scrubbed.
    dumped = cfg.model_dump_json()
    assert "1234567890abcdef1234567890abcdef12345678" not in dumped
    # Query-string oinkcode scrubbed.
    assert "LEAKY_BL_OINK" not in dumped


def test_pfblockerng_orphan_tags_have_presence_booleans():
    """Pre-v0.16.0, ``pfblockerngdnsblsafesearch`` and
    ``pfblockerngglobal`` were in CONSUMED_TAGS without any presence
    signal — they silently disappeared. v0.16.1 surfaces them."""
    xml = """
    <pfsense>
      <installedpackages>
        <pfblockerngglobal/>
        <pfblockerngdnsblsafesearch/>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    pkgs = cfg.installedpackages
    assert pkgs is not None
    pbn = pkgs.pfblockerng
    assert pbn is not None
    assert pbn.global_present is True
    assert pbn.dnsbl_safesearch_present is True


def test_frr_ospfd_interfaces_structured_with_redaction():
    """OSPFv3 interface rows under <frrospfdinterfaces> carry any
    MD5 key material through redact() — mirroring the OSPFv2
    behavior already present in FrrOspfInterface."""
    xml = """
    <pfsense>
      <installedpackages>
        <frr>
          <enable>on</enable>
        </frr>
        <frrospfdinterfaces>
          <item>
            <interface>lan</interface>
            <area>0.0.0.0</area>
            <cost>10</cost>
            <hellointerval>10</hellointerval>
            <deadinterval>40</deadinterval>
            <md5_password>LEAKY_OSPF6_KEY</md5_password>
          </item>
        </frrospfdinterfaces>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    pkgs = cfg.installedpackages
    assert pkgs is not None
    frr = pkgs.frr
    assert frr is not None
    assert len(frr.ospfd_interfaces) == 1
    row = frr.ospfd_interfaces[0]
    assert row.interface == "lan"
    assert row.area == "0.0.0.0"
    assert row.md5_password == REDACTED
    dumped = cfg.model_dump_json()
    assert "LEAKY_OSPF6_KEY" not in dumped


def test_frr_ospfd_interfaces_ospf6authkey_alias_redacts():
    """OSPFv3 builds emit the IPv6 auth key as ``<ospf6authkey>``
    rather than ``<md5_password>``. v0.16.1 added the alias to the
    parser's fallback chain; this test exercises that path end-to-end
    to prove the key still redacts when only ``ospf6authkey`` is
    present in the XML."""
    xml = """
    <pfsense>
      <installedpackages>
        <frr><enable>on</enable></frr>
        <frrospfdinterfaces>
          <item>
            <interface>lan</interface>
            <ospf6authkey>LEAKY_OSPF6_AUTHKEY</ospf6authkey>
          </item>
        </frrospfdinterfaces>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    frr = cfg.installedpackages.frr
    assert frr is not None
    assert len(frr.ospfd_interfaces) == 1
    assert frr.ospfd_interfaces[0].md5_password == REDACTED
    assert "LEAKY_OSPF6_AUTHKEY" not in cfg.model_dump_json()


def test_frr_bgp6d_sibling_tag_presence_only():
    """pfSense-FRR builds can emit ``<frrbgp6d>`` next to ``<frrbgp>``.
    v0.20.0 claims the tag (no parsing — BGP is dual-stack via
    address-families) so it doesn't leak to Other packages."""
    xml = """
    <pfsense>
      <installedpackages>
        <frr><enable>on</enable></frr>
        <frrbgp6d/>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    frr = cfg.installedpackages.frr
    assert frr is not None
    assert frr.bgp6_present is True
    unknown_tags = {u.tag for u in cfg.installedpackages.unknown}
    assert "frrbgp6d" not in unknown_tags


def test_squid_subtags_alone_still_produce_config():
    xml = """
    <pfsense>
      <installedpackages>
        <squidcache/>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    pkgs = cfg.installedpackages
    assert pkgs is not None
    assert pkgs.squid is not None
    assert pkgs.squid.cache_present is True


# ---------- v0.20.0: pfBlockerNG GeoIP continent tags -----------------------


def test_pfblockerng_geoip_continents_consumed_and_surfaced():
    """GeoIP continent blocklists each get their own top-level element
    under ``<installedpackages>``. v0.19.0 and earlier left these
    unclaimed, so any operator with GeoIP configured saw eight-plus
    leaks into the "Other packages" fallback. v0.20.0 claims them all
    and surfaces the set via ``geoip_configured`` + ``geoip_continents``."""
    xml = """
    <pfsense>
      <installedpackages>
        <pfblockerngafrica/>
        <pfblockerngeurope/>
        <pfblockerngnorthamerica/>
        <pfblockerngoceania/>
        <pfblockerngproxyandsatellite/>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    pkgs = cfg.installedpackages
    assert pkgs is not None
    pbn = pkgs.pfblockerng
    assert pbn is not None
    assert pbn.geoip_configured is True
    assert "Africa" in pbn.geoip_continents
    assert "Europe" in pbn.geoip_continents
    assert "North America" in pbn.geoip_continents
    assert "Oceania" in pbn.geoip_continents
    assert "Proxy & satellite" in pbn.geoip_continents
    # None of the GeoIP tags should leak to Other packages.
    unknown_tags = {u.tag for u in pkgs.unknown}
    for tag in (
        "pfblockerngafrica",
        "pfblockerngeurope",
        "pfblockerngnorthamerica",
        "pfblockerngoceania",
        "pfblockerngproxyandsatellite",
    ):
        assert tag not in unknown_tags, f"{tag} leaked to Other packages"


def test_pfblockerng_geoip_ocean_alias_dedupes_to_oceania():
    """Older pfBlockerNG builds spelled the continent ``ocean``; newer
    builds use ``oceania``. Both tags must be consumed and both must
    dedupe to a single "Oceania" label so upgraded configs don't show
    the continent twice."""
    xml = """
    <pfsense>
      <installedpackages>
        <pfblockerngocean/>
        <pfblockerngoceania/>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    pbn = cfg.installedpackages.pfblockerng
    assert pbn.geoip_continents.count("Oceania") == 1


# ---------- v0.20.0: Squid NTLM + Telegraf redaction ----------


def test_squidauth_ntlm_credentials_redacted():
    """v0.19.0 and earlier ignored the NTLM machine-account password
    stored under ``<squidauth><nt_pass>`` — an operator-supplied
    domain-join credential as sensitive as any other password. v0.20.0
    adds ``nt_pass`` to ``_EXACT`` and pipes the field through
    redact()."""
    xml = """
    <pfsense>
      <installedpackages>
        <squidauth>
          <auth_method>ntlm</auth_method>
          <nt_user>squid$</nt_user>
          <nt_pass>LEAKY_NT_MACHINE_PASSWORD</nt_pass>
        </squidauth>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    auth = cfg.installedpackages.squid.auth
    assert auth is not None
    assert auth.nt_user == "squid$"
    assert auth.nt_pass == REDACTED
    assert "LEAKY_NT_MACHINE_PASSWORD" not in cfg.model_dump_json()


def test_telegraf_username_redacted_and_url_basic_auth_scrubbed():
    """v0.19.0 and earlier dropped a ``<username>`` field into the
    parsed JSON unredacted while carefully redacting its paired
    ``<password>`` / ``<token>``. They are a credential pair — leaking
    one still lets someone phish or enumerate the other. v0.20.0
    redacts the username and scrubs any embedded ``user:pass@`` auth
    segment from ``<url>`` (common for InfluxDB v1)."""
    xml = """
    <pfsense>
      <installedpackages>
        <telegraf>
          <enable>on</enable>
          <url>http://LEAKY_USER:LEAKY_PASS@influx.example.com:8086/db</url>
          <username>LEAKY_INFLUX_USER</username>
          <password>LEAKY_INFLUX_PASS</password>
        </telegraf>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    tg = cfg.installedpackages.telegraf
    assert tg is not None
    assert tg.username == REDACTED
    assert tg.password == REDACTED
    # URL keeps host/path/port for diff readability; ``user:pass@``
    # segment is replaced with the standard marker.
    assert tg.url is not None
    assert "influx.example.com:8086" in tg.url
    assert "LEAKY_USER" not in tg.url
    assert "LEAKY_PASS" not in tg.url
    dumped = cfg.model_dump_json()
    assert "LEAKY_INFLUX_USER" not in dumped
    assert "LEAKY_INFLUX_PASS" not in dumped
    assert "LEAKY_USER" not in dumped
    assert "LEAKY_PASS" not in dumped


def test_telegraf_url_scrub_handles_username_only_basic_auth():
    """The URL scrub regex must also strip the degenerate ``user@``
    form (basic-auth username with no password), not just
    ``user:pass@``."""
    xml = """
    <pfsense>
      <installedpackages>
        <telegraf>
          <enable>on</enable>
          <url>http://LEAKY_BARE_USER@influx.example.com:8086/db</url>
        </telegraf>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    tg = cfg.installedpackages.telegraf
    assert tg is not None
    assert tg.url is not None
    assert "influx.example.com:8086" in tg.url
    assert "LEAKY_BARE_USER" not in tg.url


def test_telegraf_url_scrub_preserves_port_suffix_without_basic_auth():
    """URLs without basic-auth (``http://host:8086/db``) must pass
    through untouched — a too-greedy regex would swallow the port."""
    xml = """
    <pfsense>
      <installedpackages>
        <telegraf>
          <enable>on</enable>
          <url>http://influx.example.com:8086/db</url>
        </telegraf>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    tg = cfg.installedpackages.telegraf
    assert tg.url == "http://influx.example.com:8086/db"


# ---------- v0.20.0: Suricata oinkmaster regression ----------


def test_suricata_community_rules_do_not_imply_oinkmaster_configured():
    """v0.17.0 OR'd ``<snortcommunityrules>`` into the oinkmaster
    signal, so enabling the free community ruleset falsely claimed a
    paid subscription key was set. v0.20.0 narrows the signal to the
    oinkcode itself."""
    xml = """
    <pfsense>
      <installedpackages>
        <suricata>
          <snortcommunityrules>on</snortcommunityrules>
        </suricata>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    sr = cfg.installedpackages.suricata
    assert sr is not None
    assert sr.oinkmaster_configured is False


# ---------- v0.20.0: shellcmd cmdtype="disabled" ----------


def test_shellcmd_cmdtype_disabled_sets_disabled_flag():
    """The pfSense shellcmd package treats ``cmdtype="disabled"`` as
    its own disable switch, parallel to ``<disabled>on</disabled>``.
    v0.17.0 surfaced a contradictory row (``type: disabled`` paired
    with ``disabled: no``); v0.20.0 normalizes the boolean and drops
    the pseudo-type."""
    xml = """
    <pfsense>
      <installedpackages>
        <shellcmdsettings>
          <config>
            <cmd>/sbin/pfctl -F all</cmd>
            <cmdtype>disabled</cmdtype>
          </config>
        </shellcmdsettings>
      </installedpackages>
    </pfsense>
    """
    cfg = _parse(xml)
    sc = cfg.installedpackages.shellcmd
    assert sc is not None
    assert len(sc.entries) == 1
    entry = sc.entries[0]
    assert entry.disabled is True
    assert entry.cmdtype is None
