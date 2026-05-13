"""Tests for v0.43.0 — deferred package-internal parsers.

Covers the three areas the v0.42.0 plan explicitly deferred:
- HAProxy ACLs + actions per frontend, SSL detail fields, backend
  timeouts + cookie persistence + health-check tuning, global stanza
  (maxconn / nbthread / dhparam / logging / local-stats).
- Squid cache_dir + cache tuning, SSL bump fields, antivirus block,
  upstream/remote proxy.
- FRR global ACLs + prefix-lists structured as rows, OSPFv3 (frrospfd)
  daemon fields.

Each block ends with a ``LEAKY_*`` redaction assertion where the new
fields can carry secrets.
"""

from __future__ import annotations

import textwrap

from pfsense_shared.pfsense_parser import parse
from pfsense_shared.pfsense_redact import REDACTED


def _parse(xml: str):
    return parse(textwrap.dedent(xml).strip().encode())


# ---------- HAProxy: ACLs, actions, SSL, backend tuning, global -------------


HAPROXY_RICH_XML = """
<pfsense>
  <installedpackages>
    <haproxy>
      <enable>yes</enable>
      <maxconn>10000</maxconn>
      <nbthread>4</nbthread>
      <hard_stop_after>60s</hard_stop_after>
      <ssldefaultdhparam>2048</ssldefaultdhparam>
      <log-facility>local0</log-facility>
      <log-level>info</log-level>
      <localstats_port>8080</localstats_port>
      <localstats_refresh>10</localstats_refresh>
      <carpdev>opt2</carpdev>
    </haproxy>
    <ha_backends>
      <item>
        <name>fe_https</name>
        <type>http</type>
        <ssloffload/>
        <ssloffloadcert>5fa1abc</ssloffloadcert>
        <clientcert_ca>5fa1ca</clientcert_ca>
        <clientcert_crl>5fa1crl</clientcert_crl>
        <ssloffloadclientcert/>
        <ssl_ciphers>ECDHE+AESGCM:!aNULL</ssl_ciphers>
        <ssl_protocols>TLSv1.2 TLSv1.3</ssl_protocols>
        <advanced>option http-server-close</advanced>
        <a_extaddr><item><extaddr>192.0.2.10</extaddr><extaddr_port>443</extaddr_port></item></a_extaddr>
        <backend_serverpool>be_app</backend_serverpool>
        <ha_acls>
          <item>
            <name>is_api</name>
            <expression>path_beg</expression>
            <value>/api</value>
          </item>
          <item>
            <name>is_admin</name>
            <expression>hdr_dom(host)</expression>
            <value>admin.example.com</value>
            <casesensitive/>
          </item>
        </ha_acls>
        <a_actionitems>
          <item>
            <action>use_backend</action>
            <acl>is_api</acl>
            <parameters>be_api</parameters>
          </item>
          <item>
            <action>http-request set-header</action>
            <acl>is_admin</acl>
            <parameters>X-Admin true</parameters>
          </item>
        </a_actionitems>
      </item>
    </ha_backends>
    <ha_pools>
      <item>
        <name>be_app</name>
        <balance>roundrobin</balance>
        <check_type>HTTP</check_type>
        <httpcheck_method>GET</httpcheck_method>
        <monitor_uri>/health</monitor_uri>
        <connection_timeout>5000</connection_timeout>
        <server_timeout>30000</server_timeout>
        <retries>3</retries>
        <check_frequency>2000</check_frequency>
        <persist_cookie_enabled/>
        <persist_cookie_name>SRV</persist_cookie_name>
        <persist_cookie_mode>insert</persist_cookie_mode>
        <ha_servers>
          <item>
            <name>web1</name>
            <address>10.0.0.10</address>
            <port>8080</port>
            <maxconn>200</maxconn>
            <sslservercertverify/>
            <advanced>send-proxy</advanced>
            <password>LEAKY_HA_PWD</password>
          </item>
        </ha_servers>
      </item>
    </ha_pools>
  </installedpackages>
</pfsense>
"""


def test_haproxy_global_extras_parsed():
    cfg = _parse(HAPROXY_RICH_XML)
    assert cfg.installedpackages is not None
    hp = cfg.installedpackages.haproxy
    assert hp is not None
    assert hp.maxconn == "10000"
    assert hp.nbthread == "4"
    assert hp.hard_stop_after == "60s"
    assert hp.ssldefaultdhparam == "2048"
    assert hp.log_facility == "local0"
    assert hp.log_level == "info"
    assert hp.localstats_port == "8080"
    assert hp.localstats_refresh == "10"
    assert hp.carpdev == "opt2"


def test_haproxy_frontend_ssl_and_acls_actions_parsed():
    cfg = _parse(HAPROXY_RICH_XML)
    assert cfg.installedpackages is not None
    hp = cfg.installedpackages.haproxy
    assert hp is not None
    assert len(hp.frontends) == 1
    fe = hp.frontends[0]
    assert fe.ssloffloadcert == "5fa1abc"
    assert fe.clientcert_ca == "5fa1ca"
    assert fe.clientcert_crl == "5fa1crl"
    assert fe.sslclientcert_required is True
    assert fe.sslciphers == "ECDHE+AESGCM:!aNULL"
    assert fe.sslprotocols == "TLSv1.2 TLSv1.3"
    assert fe.advanced == "option http-server-close"
    assert len(fe.acls) == 2
    assert fe.acls[0].name == "is_api"
    assert fe.acls[0].expression == "path_beg"
    assert fe.acls[0].value == "/api"
    assert fe.acls[1].casesensitive is True
    assert len(fe.actions) == 2
    assert fe.actions[0].action == "use_backend"
    assert fe.actions[0].acl == "is_api"
    assert fe.actions[0].parameters == "be_api"
    assert fe.actions[1].parameters == "X-Admin true"


def test_haproxy_backend_timeouts_and_cookie_persistence():
    cfg = _parse(HAPROXY_RICH_XML)
    assert cfg.installedpackages is not None
    hp = cfg.installedpackages.haproxy
    assert hp is not None
    assert len(hp.backends) == 1
    be = hp.backends[0]
    assert be.httpcheck_method == "GET"
    assert be.monitor_uri == "/health"
    assert be.connection_timeout == "5000"
    assert be.server_timeout == "30000"
    assert be.retries == "3"
    assert be.check_interval == "2000"
    assert be.persist_cookie_enabled is True
    assert be.persist_cookie_name == "SRV"
    assert be.persist_cookie_mode == "insert"
    assert len(be.servers) == 1
    srv = be.servers[0]
    assert srv.maxconn == "200"
    assert srv.sslservercertverify is True
    assert srv.advanced == "send-proxy"
    assert srv.password == REDACTED
    assert "LEAKY_HA_PWD" not in cfg.model_dump_json()


# ---------- Squid: cache, SSL bump, antivirus, remote -----------------------


SQUID_RICH_XML = """
<pfsense>
  <installedpackages>
    <squid>
      <enable>yes</enable>
      <active_interface>lan</active_interface>
      <proxy_port>3128</proxy_port>
      <ssl_proxy>on</ssl_proxy>
      <ssl_proxy_port>3129</ssl_proxy_port>
      <ssl_proxy_intercept_interfaces>lan,opt1</ssl_proxy_intercept_interfaces>
      <dhparams_size>2048</dhparams_size>
      <sslproxy_options>NO_SSLv3,NO_TLSv1</sslproxy_options>
      <sslproxy_compatibility_mode>modern</sslproxy_compatibility_mode>
      <dca>5fb1ca</dca>
      <ssl_proxy_certref>5fb1cert</ssl_proxy_certref>
      <sslproxy_cipher>ECDHE+AESGCM</sslproxy_cipher>
    </squid>
    <squidcache>
      <enable>on</enable>
      <harddisk_cache_size>10240</harddisk_cache_size>
      <harddisk_cache_system>ufs</harddisk_cache_system>
      <harddisk_cache_location>/var/squid/cache</harddisk_cache_location>
      <minimum_object_size>0</minimum_object_size>
      <maximum_object_size>4096</maximum_object_size>
      <memory_cache_size>256</memory_cache_size>
      <maximum_objsize_in_mem>512</maximum_objsize_in_mem>
      <cache_replacement_policy>heap LFUDA</cache_replacement_policy>
      <level1_subdirs>16</level1_subdirs>
      <donotcache>.example.com
.internal</donotcache>
    </squidcache>
    <squidantivirus>
      <enable>on</enable>
      <client_info>striped</client_info>
      <enable_advanced>on</enable_advanced>
      <raw_clamd_conf>LogFile /var/log/clamd</raw_clamd_conf>
    </squidantivirus>
    <squidremote>
      <enable>on</enable>
      <proxyaddr>upstream.example.com</proxyaddr>
      <proxyport>8080</proxyport>
      <username>upstream_user</username>
      <password>LEAKY_UPSTREAM_PWD</password>
    </squidremote>
  </installedpackages>
</pfsense>
"""


def test_squid_ssl_bump_parsed():
    cfg = _parse(SQUID_RICH_XML)
    assert cfg.installedpackages is not None
    sq = cfg.installedpackages.squid
    assert sq is not None
    assert sq.squid is not None
    main = sq.squid
    assert main.ssl_proxy_enable is True
    assert main.ssl_proxy_intercept_port == "3129"
    assert main.ssl_proxy_intercept_interfaces == ["lan", "opt1"]
    assert main.ssl_proxy_dhparams_size == "2048"
    assert main.ssl_proxy_compatibility == "modern"
    assert main.ssl_proxy_cafile_ref == "5fb1ca"
    assert main.ssl_proxy_certificate_ref == "5fb1cert"
    assert main.sslproxy_cipher == "ECDHE+AESGCM"


def test_squid_cache_parsed():
    cfg = _parse(SQUID_RICH_XML)
    assert cfg.installedpackages is not None
    sq = cfg.installedpackages.squid
    assert sq is not None
    assert sq.cache is not None
    c = sq.cache
    assert c.enable is True
    assert c.harddisk_cache_size == "10240"
    assert c.harddisk_cache_system == "ufs"
    assert c.harddisk_cache_location == "/var/squid/cache"
    assert c.memory_cache_size == "256"
    assert c.cache_replacement_policy == "heap LFUDA"
    assert c.donotcache is not None
    assert ".example.com" in c.donotcache
    # Back-compat alias still works.
    assert sq.cache_present is True


def test_squid_antivirus_parsed():
    cfg = _parse(SQUID_RICH_XML)
    assert cfg.installedpackages is not None
    sq = cfg.installedpackages.squid
    assert sq is not None
    assert sq.antivirus is not None
    av = sq.antivirus
    assert av.enable is True
    assert av.client_info == "striped"
    assert av.enable_advanced is True
    assert av.raw_clamd_conf == "LogFile /var/log/clamd"
    assert sq.antivirus_present is True


def test_squid_remote_parsed_and_password_redacted():
    cfg = _parse(SQUID_RICH_XML)
    assert cfg.installedpackages is not None
    sq = cfg.installedpackages.squid
    assert sq is not None
    assert sq.remote is not None
    r = sq.remote
    assert r.enable is True
    assert r.proxyaddr == "upstream.example.com"
    assert r.proxyport == "8080"
    assert r.username == "upstream_user"
    assert r.password == REDACTED
    assert sq.remote_present is True
    assert "LEAKY_UPSTREAM_PWD" not in cfg.model_dump_json()


# ---------- FRR: ACLs, prefix-lists, OSPFv3 daemon --------------------------


FRR_RICH_XML = """
<pfsense>
  <installedpackages>
    <frr>
      <enable>on</enable>
    </frr>
    <frrglobalacls>
      <item>
        <name>RFC1918</name>
        <seq>10</seq>
        <action>permit</action>
        <source>10.0.0.0/8</source>
        <descr>private 10</descr>
      </item>
      <item>
        <name>RFC1918</name>
        <seq>20</seq>
        <action>permit</action>
        <source>192.168.0.0/16</source>
      </item>
      <item>
        <name>DENY_ALL</name>
        <seq>10</seq>
        <action>deny</action>
        <source>any</source>
      </item>
    </frrglobalacls>
    <frrglobalprefixes>
      <item>
        <name>CUST_RANGES</name>
        <seq>10</seq>
        <action>permit</action>
        <source>198.51.100.0/24</source>
        <ge>24</ge>
        <le>32</le>
      </item>
      <item>
        <name>CUST_RANGES</name>
        <seq>20</seq>
        <action>deny</action>
        <source>0.0.0.0/0</source>
        <le>32</le>
      </item>
    </frrglobalprefixes>
    <frrospfd>
      <enable>on</enable>
      <router_id>10.0.0.1</router_id>
      <redistribute_connected>on</redistribute_connected>
      <redistribute_static>on</redistribute_static>
    </frrospfd>
  </installedpackages>
</pfsense>
"""


def test_frr_global_acls_parsed_as_rows():
    cfg = _parse(FRR_RICH_XML)
    assert cfg.installedpackages is not None
    frr = cfg.installedpackages.frr
    assert frr is not None
    assert frr.global_acls_present is True
    assert len(frr.global_acls) == 3
    rfc1918 = [a for a in frr.global_acls if a.name == "RFC1918"]
    assert len(rfc1918) == 2
    assert rfc1918[0].seq == "10"
    assert rfc1918[0].action == "permit"
    assert rfc1918[0].source == "10.0.0.0/8"
    deny = [a for a in frr.global_acls if a.name == "DENY_ALL"][0]
    assert deny.action == "deny"
    assert deny.source == "any"


def test_frr_global_prefixes_parsed_as_rows():
    cfg = _parse(FRR_RICH_XML)
    assert cfg.installedpackages is not None
    frr = cfg.installedpackages.frr
    assert frr is not None
    assert frr.global_prefixes_present is True
    assert len(frr.global_prefixes) == 2
    first = frr.global_prefixes[0]
    assert first.name == "CUST_RANGES"
    assert first.action == "permit"
    assert first.prefix == "198.51.100.0/24"
    assert first.ge == "24"
    assert first.le == "32"


def test_frr_ospfd_daemon_parsed():
    cfg = _parse(FRR_RICH_XML)
    assert cfg.installedpackages is not None
    frr = cfg.installedpackages.frr
    assert frr is not None
    assert frr.ospfd_present is True
    assert frr.ospfd is not None
    o6 = frr.ospfd
    assert o6.enabled is True
    assert o6.router_id == "10.0.0.1"
    assert o6.redistribute_connected is True
    assert o6.redistribute_static is True
    assert o6.redistribute_kernel is False
