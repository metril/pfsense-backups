"""Parses ``<apikeys>`` — pfSense webGUI API access tokens.

Each entry ties a user to an API key + secret pair that the
webGUI accepts for automation. The secret half is redacted; the
public key id + owner + descr stay visible so diffs can flag
"this user grew a new API credential" without leaking the token.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact

from ._helpers import children, text


class ApiKeyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Stable key for diffing — apikey id stays visible, secret half
    # redacts. pfSense uses the public id as the diff-stable handle.
    key: str
    username: str | None = None
    descr: str | None = None
    apikey: str | None = None
    apisecret: str | None = None


def parse(root: Element) -> list[ApiKeyEntry]:
    el = root.find("apikeys")
    if el is None:
        return []
    out: list[ApiKeyEntry] = []
    # pfSense wraps each entry in ``<item>`` under ``<apikeys>``.
    for it in children(el, "item"):
        apikey = text(it, "apikey") or text(it, "key")
        if not apikey:
            continue
        out.append(
            ApiKeyEntry(
                key=apikey,
                username=text(it, "username") or text(it, "user"),
                descr=text(it, "descr") or text(it, "description"),
                # The public half is an identifier, keep it visible.
                apikey=apikey,
                # The secret half pairs with it; redact via a
                # self-documenting tag name.
                apisecret=redact(
                    "api_secret",
                    text(it, "apisecret") or text(it, "secret"),
                ),
            )
        )
    return out
