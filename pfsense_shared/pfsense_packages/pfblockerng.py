"""Parses pfBlockerNG config under ``<installedpackages>``.

pfBlockerNG spreads itself across several sibling tags: ``pfblockerng``
(global), ``pfblockerngipsettings`` (IP rules), ``pfblockerngdnsblsettings``
(DNSBL / DoH), ``pfblockernglistsv4`` / ``pfblockernglistsv6`` (feeds).
We collect the common review-worthy fields; the rest stays available
via the raw-XML fallback tab.
"""

from __future__ import annotations

import re
from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_sections._helpers import bool_flag, children, text

# Feeds from paid subscribers (ET Pro, Snort VRT) embed the operator's
# credential directly in the URL path. The standard shape is:
#   https://rules.emergingthreats.net/<40-hex-char-oinkcode>/…
#   https://www.snort.org/rules/snortrules-snapshot-XXXX.tar.gz?oinkcode=…
# Redact both forms so the credential never lands in parsed JSON.
_OINKCODE_PATH_RE = re.compile(r"/([0-9a-fA-F]{30,64})/")
_OINKCODE_QUERY_RE = re.compile(r"([?&]oinkcode=)[^&]+", re.IGNORECASE)


def _scrub_feed_url(url: str | None) -> str | None:
    """Strip subscriber credentials from a feed URL while keeping the
    rest of the URL readable in diffs. The placeholder is stable so
    diffing two backups still shows "same feed" when only the path
    credential rotates."""
    if not url:
        return url
    scrubbed = _OINKCODE_PATH_RE.sub("/***oinkcode***/", url)
    scrubbed = _OINKCODE_QUERY_RE.sub(r"\1***redacted***", scrubbed)
    return scrubbed


class PfBlockerNgFeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Stable key: header ("aliasname" in raw XML) + url pair; multiple
    # feeds can share a header (they compile into one alias).
    key: str
    header: str | None = None
    state: str | None = None  # Enabled | Disabled | Hold | Deny
    format: str | None = None
    action: str | None = None  # Unbound / Alias Deny / Alias Permit / ...
    url: str | None = None


class PfBlockerNgConfig(BaseModel):
    """Global + per-feature switch state for pfBlockerNG."""

    model_config = ConfigDict(extra="forbid")

    enable_pfblockerng: bool = False
    keep_settings: bool = False
    pfb_interface: str | None = None
    pfb_inbound: str | None = None
    pfb_outbound: str | None = None
    # IP rules
    ip_enabled: bool = False
    ipv6_enabled: bool = False
    maxmind_key_configured: bool = False  # True if MaxMind key was set
    # DNSBL
    dnsbl_enabled: bool = False
    dnsbl_mode: str | None = None  # unbound_python | dnsbl_unified | ...
    dnsbl_port: str | None = None
    # Feeds flattened across v4 + v6 + DNSBL list tags.
    feeds: list[PfBlockerNgFeed] = []


# Tags this parser consumes out of <installedpackages>. Any tag in this
# set will not appear in the UI's "Other packages" fallback.
CONSUMED_TAGS = frozenset(
    {
        "pfblockerng",
        "pfblockerngipsettings",
        "pfblockerngdnsblsettings",
        "pfblockernglistsv4",
        "pfblockernglistsv6",
        "pfblockerngdnsbl",
        "pfblockerngdnsblsafesearch",
        "pfblockerngglobal",
    }
)


def _collect_feeds(el: Element | None, container_tag: str, row_tag: str) -> list[PfBlockerNgFeed]:
    if el is None:
        return []
    out: list[PfBlockerNgFeed] = []
    for lst in children(el, container_tag):
        header = text(lst, "aliasname")
        for row in children(lst, row_tag):
            url = _scrub_feed_url(text(row, "url"))
            if not url:
                continue
            out.append(
                PfBlockerNgFeed(
                    key=f"{header or '?'}|{url}",
                    header=header,
                    state=text(row, "state"),
                    format=text(row, "format"),
                    action=text(lst, "action"),
                    url=url,
                )
            )
    return out


def parse(ip: Element) -> PfBlockerNgConfig | None:
    """``ip`` is the ``<installedpackages>`` element."""
    pbn = ip.find("pfblockerng")
    ipset = ip.find("pfblockerngipsettings")
    dnsblset = ip.find("pfblockerngdnsblsettings")
    listsv4 = ip.find("pfblockernglistsv4")
    listsv6 = ip.find("pfblockernglistsv6")
    dnsbl_feeds = ip.find("pfblockerngdnsbl")

    if all(
        x is None
        for x in (pbn, ipset, dnsblset, listsv4, listsv6, dnsbl_feeds)
    ):
        return None

    feeds: list[PfBlockerNgFeed] = []
    feeds.extend(_collect_feeds(listsv4, "config", "row"))
    feeds.extend(_collect_feeds(listsv6, "config", "row"))
    feeds.extend(_collect_feeds(dnsbl_feeds, "config", "row"))

    # MaxMind key redaction: we report "configured" / "not configured"
    # rather than carrying the key through the parser at all.
    maxmind_key_configured = False
    if ipset is not None:
        maxmind_key_configured = bool((text(ipset, "maxmind_key") or "").strip())

    return PfBlockerNgConfig(
        enable_pfblockerng=bool_flag(pbn, "enable_cb") if pbn is not None else False,
        keep_settings=bool_flag(pbn, "keep") if pbn is not None else False,
        pfb_interface=text(pbn, "inbound_interface") if pbn is not None else None,
        pfb_inbound=text(pbn, "inbound_deny_action") if pbn is not None else None,
        pfb_outbound=text(pbn, "outbound_deny_action") if pbn is not None else None,
        ip_enabled=bool_flag(ipset, "enable_cb") if ipset is not None else False,
        ipv6_enabled=bool_flag(ipset, "ipv6usage") if ipset is not None else False,
        maxmind_key_configured=maxmind_key_configured,
        dnsbl_enabled=bool_flag(dnsblset, "dnsbl") if dnsblset is not None else False,
        dnsbl_mode=text(dnsblset, "dnsbl_mode") if dnsblset is not None else None,
        dnsbl_port=text(dnsblset, "dnsbl_port") if dnsblset is not None else None,
        feeds=feeds,
    )
