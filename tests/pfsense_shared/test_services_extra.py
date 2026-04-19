"""Tests for v0.11.2 sections: NTP, SNMP, syslog, DHCP relay, schedules,
shaper, dnshaper, load balancer, captive portal.
"""

from __future__ import annotations

import textwrap

from pfsense_shared.pfsense_diff import diff_configs
from pfsense_shared.pfsense_parser import parse
from pfsense_shared.pfsense_redact import REDACTED


def _parse(xml: str):
    return parse(textwrap.dedent(xml).strip().encode())


def test_snmpd_communities_redacted() -> None:
    cfg = _parse("""
        <pfsense>
          <snmpd>
            <enable/>
            <syslocation>dc1</syslocation>
            <syscontact>noc@example</syscontact>
            <rocommunity>leaky_ro_community</rocommunity>
            <rwcommunity>leaky_rw_community</rwcommunity>
            <pollport>161</pollport>
            <trapenable/>
            <trapserver>10.0.0.10</trapserver>
            <trapserverport>162</trapserverport>
          </snmpd>
        </pfsense>
    """)
    s = cfg.snmpd
    assert s is not None
    assert s.rocommunity == REDACTED
    assert s.rwcommunity == REDACTED
    assert s.trapenable is True
    # Leak check
    assert "leaky_ro_community" not in cfg.model_dump_json()
    assert "leaky_rw_community" not in cfg.model_dump_json()


def test_ntpd_config() -> None:
    cfg = _parse("""
        <pfsense>
          <ntpd>
            <enable/>
            <interface>lan,opt1</interface>
            <timeservers>0.pool.ntp.org 1.pool.ntp.org</timeservers>
            <orphan>12</orphan>
          </ntpd>
        </pfsense>
    """)
    n = cfg.ntpd
    assert n is not None
    assert n.enable is True
    assert n.interfaces == ["lan", "opt1"]
    assert n.timeservers == ["0.pool.ntp.org", "1.pool.ntp.org"]
    assert n.orphan == "12"


def test_syslog_hosts_and_filters() -> None:
    cfg = _parse("""
        <pfsense>
          <syslog>
            <enable/>
            <reverse/>
            <remoteserver>10.0.0.5:514</remoteserver>
            <remoteserver2>10.0.0.6:514</remoteserver2>
            <filter/>
            <system/>
            <vpn/>
          </syslog>
        </pfsense>
    """)
    s = cfg.syslog
    assert s is not None
    assert s.enable is True
    assert s.reverse is True
    assert [h.host for h in s.hosts] == ["10.0.0.5:514", "10.0.0.6:514"]
    assert s.filter_ is True
    assert s.system is True
    assert s.vpn is True
    assert s.dhcp is False


def test_dhcp_relay_parses_both_stacks() -> None:
    cfg = _parse("""
        <pfsense>
          <dhcrelay>
            <enable/>
            <interface>lan,opt1</interface>
            <server>10.0.0.1</server>
          </dhcrelay>
          <dhcrelay6>
            <enable/>
            <interface>lan</interface>
            <server>fe80::1%lan</server>
          </dhcrelay6>
        </pfsense>
    """)
    kinds = [r.kind for r in cfg.dhcp_relays]
    assert kinds == ["ipv4", "ipv6"]
    assert cfg.dhcp_relays[0].interface == ["lan", "opt1"]
    assert cfg.dhcp_relays[1].server == ["fe80::1%lan"]


def test_schedules() -> None:
    cfg = _parse("""
        <pfsense>
          <schedules>
            <schedule>
              <name>work-hours</name>
              <descr>M-F 9-5</descr>
              <timerange>
                <day>1,2,3,4,5</day>
                <hour>9:00-17:00</hour>
              </timerange>
            </schedule>
          </schedules>
        </pfsense>
    """)
    assert len(cfg.schedules) == 1
    s = cfg.schedules[0]
    assert s.name == "work-hours"
    assert s.time_ranges
    assert "9:00-17:00" in s.time_ranges[0]


def test_shaper_queues_flatten_nested_tree() -> None:
    cfg = _parse("""
        <pfsense>
          <shaper>
            <queue>
              <name>root</name>
              <interface>wan</interface>
              <queue>
                <name>web</name>
                <bandwidth>50</bandwidth>
                <bandwidthtype>Mb</bandwidthtype>
              </queue>
              <queue>
                <name>voice</name>
                <priority>7</priority>
              </queue>
            </queue>
          </shaper>
        </pfsense>
    """)
    names = [q.name for q in cfg.shaper_queues]
    assert names == ["root", "web", "voice"]


def test_dnshaper_pipes() -> None:
    cfg = _parse("""
        <pfsense>
          <dnshaper>
            <pipe><name>p1</name><number>1</number><bandwidth>100</bandwidth></pipe>
            <pipe><name>p2</name><number>2</number><bandwidth>200</bandwidth></pipe>
          </dnshaper>
        </pfsense>
    """)
    assert [p.name for p in cfg.dnshaper_pipes] == ["p1", "p2"]
    assert cfg.dnshaper_pipes[0].bandwidth == "100"


def test_load_balancer_pools_and_virtual_servers() -> None:
    cfg = _parse("""
        <pfsense>
          <load_balancer>
            <lbpool>
              <name>web-pool</name>
              <behaviour>balance</behaviour>
              <port>80</port>
              <monitor>HTTP</monitor>
              <servers>10.0.0.10|80 10.0.0.11|80</servers>
            </lbpool>
            <virtual_server>
              <name>web-vs</name>
              <ipaddr>192.0.2.1</ipaddr>
              <port>80</port>
              <poolname>web-pool</poolname>
            </virtual_server>
          </load_balancer>
        </pfsense>
    """)
    assert len(cfg.lb_pools) == 1
    assert cfg.lb_pools[0].behaviour == "balance"
    assert [m.ip for m in cfg.lb_pools[0].servers] == ["10.0.0.10", "10.0.0.11"]
    assert len(cfg.lb_virtual_servers) == 1
    assert cfg.lb_virtual_servers[0].poolname == "web-pool"


def test_captive_portal_radius_secret_redacted() -> None:
    cfg = _parse("""
        <pfsense>
          <captiveportal>
            <guest>
              <zoneid>2</zoneid>
              <enable/>
              <interface>opt2</interface>
              <auth_method>radius</auth_method>
              <radius_secret>leaky_portal_secret</radius_secret>
              <redirurl>https://welcome.example</redirurl>
            </guest>
          </captiveportal>
        </pfsense>
    """)
    assert len(cfg.captive_portal_zones) == 1
    z = cfg.captive_portal_zones[0]
    assert z.zone == "guest"
    assert z.enable is True
    assert z.auth_method == "radius"
    assert z.radius_secret == REDACTED
    assert "leaky_portal_secret" not in cfg.model_dump_json()


def test_diff_services_extra_added_modified() -> None:
    a = _parse("""
        <pfsense>
          <ntpd><enable/><interface>lan</interface></ntpd>
          <schedules>
            <schedule>
              <name>s1</name>
              <timerange><day>1</day><hour>9:00-17:00</hour></timerange>
            </schedule>
          </schedules>
        </pfsense>
    """)
    b = _parse("""
        <pfsense>
          <ntpd><enable/><interface>lan,opt1</interface></ntpd>
          <schedules>
            <schedule>
              <name>s1</name>
              <timerange><day>1</day><hour>9:00-18:00</hour></timerange>
            </schedule>
            <schedule>
              <name>s2</name>
              <timerange><day>6</day><hour>10:00-12:00</hour></timerange>
            </schedule>
          </schedules>
          <snmpd><enable/><syslocation>dc1</syslocation></snmpd>
        </pfsense>
    """)
    d = diff_configs(a, b)
    # ntpd modified (interfaces changed)
    assert len(d.ntpd.modified) == 1
    # schedules: 1 added, 1 modified
    assert len(d.schedules.added) == 1
    assert len(d.schedules.modified) == 1
    assert d.schedules.added[0]["name"] == "s2"
    # snmpd added
    assert len(d.snmpd.added) == 1
