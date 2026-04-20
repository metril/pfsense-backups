"""Parses FreeRADIUS package config under ``<installedpackages>``.

pfSense's FreeRADIUS package uses multiple sibling tags to store
server + clients + users. All shared secrets (NAS shared secrets,
RADIUS clients) and user passwords are redacted.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact
from pfsense_shared.pfsense_sections._helpers import bool_flag, children, text


class FreeRadiusClient(BaseModel):
    """A NAS client authorised to send Access-Request to this server."""

    model_config = ConfigDict(extra="forbid")

    name: str
    ipaddr: str | None = None
    shortname: str | None = None
    # Redacted — the shared secret with the NAS.
    shared_secret: str | None = None
    nas_type: str | None = None
    descr: str | None = None


class FreeRadiusUser(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    # Redacted
    password: str | None = None
    auth_type: str | None = None
    expiration: str | None = None
    descr: str | None = None


class FreeRadiusInterface(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Stable key: bind IP + port
    key: str
    ipaddr: str | None = None
    port: str | None = None
    ip_type: str | None = None  # "auth" | "acct" | "status"
    interface_type: str | None = None


class FreeRadiusConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    interfaces: list[FreeRadiusInterface] = []
    clients: list[FreeRadiusClient] = []
    users: list[FreeRadiusUser] = []


CONSUMED_TAGS = frozenset({"freeradius", "freeradiussettings"})


def parse(ip: Element) -> FreeRadiusConfig | None:
    settings_el = ip.find("freeradiussettings")
    fr_el = ip.find("freeradius")
    if settings_el is None and fr_el is None:
        return None

    enabled = False
    if settings_el is not None:
        enabled = bool_flag(settings_el, "enable") or bool_flag(settings_el, "varsettingsenable")

    interfaces: list[FreeRadiusInterface] = []
    clients: list[FreeRadiusClient] = []
    users: list[FreeRadiusUser] = []

    # The FreeRADIUS pfSense package uses a flat record list inside
    # <freeradius><config>... where each record has a "section" field
    # telling us which role (interfaces/clients/users) it fills.
    if fr_el is not None:
        for rec in children(fr_el, "config"):
            section = (text(rec, "varsection") or text(rec, "section") or "").lower()
            if "interface" in section:
                ip_addr = text(rec, "varinterfaceipaddress") or text(rec, "ipaddr")
                port = text(rec, "varinterfaceport") or text(rec, "port")
                interfaces.append(
                    FreeRadiusInterface(
                        key=f"{ip_addr or '?'}:{port or '?'}",
                        ipaddr=ip_addr,
                        port=port,
                        ip_type=text(rec, "varinterfaceiptype"),
                        interface_type=text(rec, "varinterfacetype"),
                    )
                )
            elif "client" in section or "nas" in section:
                name = (
                    text(rec, "varclientname")
                    or text(rec, "varclientip")
                    or text(rec, "name")
                    or "?"
                )
                clients.append(
                    FreeRadiusClient(
                        name=name,
                        ipaddr=text(rec, "varclientip") or text(rec, "ipaddr"),
                        shortname=text(rec, "varclientshortname"),
                        shared_secret=redact(
                            "shared_secret",
                            text(rec, "varclientsharedsecret")
                            or text(rec, "shared_secret"),
                        ),
                        nas_type=text(rec, "varclientnastype"),
                        descr=text(rec, "varclientdescription") or text(rec, "descr"),
                    )
                )
            elif "user" in section:
                name = text(rec, "varusersname") or text(rec, "name") or "?"
                users.append(
                    FreeRadiusUser(
                        name=name,
                        password=redact(
                            "user_password",
                            text(rec, "varuserspassword")
                            or text(rec, "user_password"),
                        ),
                        auth_type=text(rec, "varusersauthtype"),
                        expiration=text(rec, "varusersexpiration"),
                        descr=text(rec, "varusersdescription") or text(rec, "descr"),
                    )
                )

    return FreeRadiusConfig(
        enabled=enabled,
        interfaces=interfaces,
        clients=clients,
        users=users,
    )
