"""Tests for v0.12.0 section parsers.

Covers: dyndns, notifications (SMTP/Pushover/Slack/Telegram/Growl),
laggs (layer2 extension), CRL (pki extension), IGMP proxy, radvd,
UPS, voucher rolls, FTP proxy. Every secret field that lands in
these parsers is asserted not to leak into the JSON serialization.
"""

from __future__ import annotations

import textwrap

from pfsense_shared.pfsense_diff import diff_configs
from pfsense_shared.pfsense_parser import parse
from pfsense_shared.pfsense_redact import REDACTED


def _parse(xml: str):
    return parse(textwrap.dedent(xml).strip().encode())


def test_dyndns_provider_and_password_redaction() -> None:
    cfg = _parse("""
        <pfsense>
          <dyndnses>
            <dyndns>
              <type>cloudflare</type>
              <interface>wan</interface>
              <host>gw</host>
              <domainname>example.com</domainname>
              <username>public_account_id</username>
              <password>LEAKY_DDNS_API_TOKEN</password>
              <enable/>
            </dyndns>
          </dyndnses>
        </pfsense>
    """)
    assert len(cfg.dyndns_entries) == 1
    d = cfg.dyndns_entries[0]
    assert d.type == "cloudflare"
    assert d.host == "gw"
    assert d.domainname == "example.com"
    # Username stays visible (public id)
    assert d.username == "public_account_id"
    # Password redacted
    assert d.password == REDACTED
    assert "LEAKY_DDNS_API_TOKEN" not in cfg.model_dump_json()


def test_notifications_smtp_pushover_and_slack_redacted() -> None:
    cfg = _parse("""
        <pfsense>
          <notifications>
            <smtp>
              <ipaddress>smtp.example</ipaddress>
              <port>587</port>
              <ssl/>
              <fromaddress>noc@example</fromaddress>
              <username>alerts</username>
              <password>LEAKY_SMTP_PW</password>
            </smtp>
            <pushover>
              <api_key>LEAKY_PUSHOVER_APIKEY</api_key>
              <user_key>LEAKY_PUSHOVER_USERKEY</user_key>
            </pushover>
            <slack>
              <enable/>
              <webhook_url>https://hooks.slack/LEAKY_SLACK_TOKEN</webhook_url>
            </slack>
            <telegram>
              <enable/>
              <chat_id>12345</chat_id>
              <api_token>LEAKY_TELEGRAM_BOT_TOKEN</api_token>
            </telegram>
          </notifications>
        </pfsense>
    """)
    n = cfg.notifications
    assert n is not None
    assert n.smtp is not None
    assert n.smtp.ipaddress == "smtp.example"
    assert n.smtp.password == REDACTED
    assert n.pushover is not None
    assert n.pushover.api_key == REDACTED
    assert n.pushover.user_key == REDACTED
    assert n.slack is not None
    assert n.slack.webhook_url == REDACTED
    assert n.telegram is not None
    assert n.telegram.chat_id == "12345"
    assert n.telegram.api_token == REDACTED

    blob = cfg.model_dump_json()
    for leak in (
        "LEAKY_SMTP_PW",
        "LEAKY_PUSHOVER_APIKEY",
        "LEAKY_PUSHOVER_USERKEY",
        "LEAKY_SLACK_TOKEN",
        "LEAKY_TELEGRAM_BOT_TOKEN",
    ):
        assert leak not in blob, f"{leak!r} leaked"


def test_laggs_parse_and_member_list() -> None:
    cfg = _parse("""
        <pfsense>
          <laggs>
            <lagg>
              <laggif>lagg0</laggif>
              <members>em0,em1</members>
              <proto>lacp</proto>
              <descr>uplink</descr>
            </lagg>
            <lagg>
              <laggif>lagg1</laggif>
              <members>em2</members>
              <proto>failover</proto>
            </lagg>
          </laggs>
        </pfsense>
    """)
    assert [la.laggif for la in cfg.laggs] == ["lagg0", "lagg1"]
    assert cfg.laggs[0].members == ["em0", "em1"]
    assert cfg.laggs[0].proto == "lacp"
    assert cfg.laggs[1].members == ["em2"]


def test_crl_entries_and_revoked_cert_refids() -> None:
    cfg = _parse("""
        <pfsense>
          <ca><refid>ca1</refid><descr>CA</descr><crt>AAAA</crt></ca>
          <crl>
            <refid>crl1</refid>
            <descr>revoked certs</descr>
            <caref>ca1</caref>
            <method>internal</method>
            <cert><refid>bad-cert-1</refid></cert>
            <cert><refid>bad-cert-2</refid></cert>
          </crl>
        </pfsense>
    """)
    assert len(cfg.crls) == 1
    crl = cfg.crls[0]
    assert crl.refid == "crl1"
    assert crl.caref == "ca1"
    assert crl.method == "internal"
    assert crl.revoked_cert_refids == ["bad-cert-1", "bad-cert-2"]


def test_igmpproxy_entries() -> None:
    cfg = _parse("""
        <pfsense>
          <igmpproxy>
            <item><type>upstream</type><ifname>wan</ifname></item>
            <item><type>downstream</type><ifname>lan</ifname><network>239.0.0.0/8</network></item>
          </igmpproxy>
        </pfsense>
    """)
    assert len(cfg.igmpproxy_entries) == 2
    up = cfg.igmpproxy_entries[0]
    assert up.type == "upstream"
    assert up.ifname == "wan"
    dn = cfg.igmpproxy_entries[1]
    assert dn.networks == ["239.0.0.0/8"]


def test_radvd_interfaces() -> None:
    cfg = _parse("""
        <pfsense>
          <radvd>
            <lan>
              <ramode>unmanaged</ramode>
              <rapriority>medium</rapriority>
              <radns>2001:db8::1 2001:db8::2</radns>
            </lan>
            <opt1>
              <ramode>disabled</ramode>
            </opt1>
          </radvd>
        </pfsense>
    """)
    keys = [r.interface for r in cfg.radvd_interfaces]
    assert keys == ["lan", "opt1"]
    assert cfg.radvd_interfaces[0].radns == ["2001:db8::1", "2001:db8::2"]
    assert cfg.radvd_interfaces[1].ramode == "disabled"


def test_ups_config_redacts_remote_password() -> None:
    cfg = _parse("""
        <pfsense>
          <ups>
            <enable/>
            <driver>usbhid-ups</driver>
            <port>auto</port>
            <upsname>mainups</upsname>
            <remoteuser>monitor</remoteuser>
            <remotepassword>LEAKY_UPS_PW</remotepassword>
          </ups>
        </pfsense>
    """)
    assert cfg.ups is not None
    assert cfg.ups.enable is True
    assert cfg.ups.driver == "usbhid-ups"
    assert cfg.ups.remotepassword == REDACTED
    assert "LEAKY_UPS_PW" not in cfg.model_dump_json()


def test_voucher_rolls() -> None:
    cfg = _parse("""
        <pfsense>
          <voucher>
            <roll><number>1</number><minutes>60</minutes><count>100</count><descr>guest</descr></roll>
            <roll><number>2</number><minutes>1440</minutes><count>50</count></roll>
          </voucher>
        </pfsense>
    """)
    assert [v.number for v in cfg.voucher_rolls] == ["1", "2"]
    assert cfg.voucher_rolls[0].descr == "guest"


def test_ftpproxy_is_optional_and_parses() -> None:
    empty = _parse("<pfsense></pfsense>")
    assert empty.ftpproxy is None

    with_ftp = _parse("""
        <pfsense>
          <ftpproxy>
            <enable/>
            <ports>21</ports>
            <interface>wan</interface>
          </ftpproxy>
        </pfsense>
    """)
    assert with_ftp.ftpproxy is not None
    assert with_ftp.ftpproxy.enable is True
    assert with_ftp.ftpproxy.ports == "21"


def test_diff_detects_dyndns_and_lagg_changes() -> None:
    a = _parse("""
        <pfsense>
          <dyndnses>
            <dyndns><type>cloudflare</type><host>gw</host></dyndns>
          </dyndnses>
          <laggs>
            <lagg><laggif>lagg0</laggif><members>em0,em1</members><proto>lacp</proto></lagg>
          </laggs>
        </pfsense>
    """)
    b = _parse("""
        <pfsense>
          <dyndnses>
            <dyndns><type>cloudflare</type><host>gw</host></dyndns>
            <dyndns><type>duckdns</type><host>fallback</host></dyndns>
          </dyndnses>
          <laggs>
            <lagg><laggif>lagg0</laggif><members>em0,em1,em2</members><proto>lacp</proto></lagg>
          </laggs>
        </pfsense>
    """)
    d = diff_configs(a, b)
    assert len(d.dyndns_entries.added) == 1
    assert d.dyndns_entries.added[0]["host"] == "fallback"
    assert len(d.laggs.modified) == 1
    assert any(c.field == "members" for c in d.laggs.modified[0].changes)
