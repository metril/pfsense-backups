"""Parses ``<installedpackages>`` — dispatches to per-package parsers.

Known packages (pfBlockerNG, HAProxy, Suricata, ACME) get structured
Pydantic output. Unknown / unsupported packages are captured as
``UnknownPackage`` entries with the raw XML subtree + entry count so
the UI can show "this package is installed but not parsed yet"
without hiding it.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element, tostring

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_packages import acme as _acme
from pfsense_shared.pfsense_packages import haproxy as _haproxy
from pfsense_shared.pfsense_packages import pfblockerng as _pfblockerng
from pfsense_shared.pfsense_packages import suricata as _suricata
from pfsense_shared.pfsense_packages.acme import AcmeConfig
from pfsense_shared.pfsense_packages.haproxy import HaProxyConfig
from pfsense_shared.pfsense_packages.pfblockerng import PfBlockerNgConfig
from pfsense_shared.pfsense_packages.suricata import SuricataConfig


class UnknownPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Stable key: the top-level tag name. pfSense uses the tag itself
    # as the "package name" under <installedpackages>.
    tag: str
    entry_count: int  # number of direct child elements
    xml: str  # raw XML subtree for the UI fallback


class InstalledPackages(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pfblockerng: PfBlockerNgConfig | None = None
    haproxy: HaProxyConfig | None = None
    suricata: SuricataConfig | None = None
    acme: AcmeConfig | None = None
    unknown: list[UnknownPackage] = []


# Tags consumed by the known-package parsers. Anything outside this set
# under <installedpackages> falls into ``unknown``.
_CONSUMED: frozenset[str] = (
    _pfblockerng.CONSUMED_TAGS
    | _haproxy.CONSUMED_TAGS
    | _suricata.CONSUMED_TAGS
    | _acme.CONSUMED_TAGS
)


def parse(root: Element) -> InstalledPackages | None:
    el = root.find("installedpackages")
    if el is None or len(list(el)) == 0:
        return None

    pbn = _pfblockerng.parse(el)
    hp = _haproxy.parse(el)
    sr = _suricata.parse(el)
    acme_cfg = _acme.parse(el)

    unknown: list[UnknownPackage] = []
    seen: set[str] = set()
    for child in list(el):
        tag = child.tag
        if tag in _CONSUMED or tag in seen:
            continue
        seen.add(tag)
        unknown.append(
            UnknownPackage(
                tag=tag,
                entry_count=len(list(child)),
                xml=tostring(child, encoding="unicode"),
            )
        )

    if all(
        x is None for x in (pbn, hp, sr, acme_cfg)
    ) and not unknown:
        return None

    return InstalledPackages(
        pfblockerng=pbn,
        haproxy=hp,
        suricata=sr,
        acme=acme_cfg,
        unknown=unknown,
    )
