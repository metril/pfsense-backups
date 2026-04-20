"""Tests for v0.16.0 — pfBlockerNG / FRR / Squid sub-tag consumption.

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
"""

from __future__ import annotations

import textwrap

from pfsense_shared.pfsense_parser import parse


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
    assert sq.auth_present is True
    assert sq.antivirus_present is True


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
