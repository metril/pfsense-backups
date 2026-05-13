"""Parses users, groups, and external auth servers.

All secrets run through the redaction helper: bcrypt password hashes,
RADIUS shared secrets, LDAP bind passwords.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact

from ._helpers import bool_flag, children, text


class User(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    uid: str | None = None
    scope: str | None = None  # "user" | "system"
    descr: str | None = None
    # bcrypt hash — always redacted.
    bcrypt_hash: str | None = None
    disabled: bool = False
    # Groupname refs — pfSense stores these as parallel <groupname> repeats
    groups: list[str] = []
    # Cert refids (references into <cert> entries)
    certrefs: list[str] = []
    expires: str | None = None
    # v0.42.0 — TOTP seed (redacted; equivalent to a password — anyone
    # holding it can mint valid 2FA codes), U2F/WebAuthn key handles
    # (not directly secret but worth surfacing), and the user's SSH
    # public key (identity, not a secret — but bulky so we still
    # expose it so the reviewer can see who has shell access).
    otp_seed: str | None = None  # redacted
    u2f_keys: list[str] = []
    ssh_key: str | None = None


class Group(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    gid: str | None = None
    scope: str | None = None
    description: str | None = None
    # Permission strings (pfSense "priv" list).
    privs: list[str] = []
    # Member usernames.
    members: list[str] = []


class AuthServer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: str | None = None  # "ldap" | "radius"
    host: str | None = None
    port: str | None = None
    # redacted
    ldap_bindpw: str | None = None
    radius_secret: str | None = None
    # LDAP-specific
    ldap_binddn: str | None = None
    ldap_basedn: str | None = None
    ldap_scope: str | None = None
    ldap_authcn: str | None = None


def parse_users(root: Element) -> list[User]:
    # pfSense stores users under <system><user>...</user></system>.
    sys_el = root.find("system")
    if sys_el is None:
        return []
    out: list[User] = []
    for u in children(sys_el, "user"):
        name = text(u, "name")
        if not name:
            continue
        groups = [e.text or "" for e in children(u, "groupname") if e.text]
        certrefs = [e.text or "" for e in children(u, "cert") if e.text]
        # pfSense stores U2F enrolled credentials under <u2f_keys> with
        # one <item> per registered authenticator. We capture the key
        # handles (not the public keys — neither is a secret on its
        # own, but the handles are what's visible in the UI).
        u2f_keys: list[str] = []
        u2f_block = u.find("u2f_keys")
        if u2f_block is not None:
            for item in children(u2f_block, "item"):
                kh = text(item, "keyHandle") or text(item, "keyhandle")
                if kh:
                    u2f_keys.append(kh)
        bhash = text(u, "bcrypt-hash") or text(u, "password")
        out.append(
            User(
                name=name,
                uid=text(u, "uid"),
                scope=text(u, "scope"),
                descr=text(u, "descr"),
                bcrypt_hash=redact("bcrypt_hash", bhash),
                disabled=bool_flag(u, "disabled"),
                groups=groups,
                certrefs=certrefs,
                expires=text(u, "expires"),
                otp_seed=redact("otp_seed", text(u, "otp_seed")),
                u2f_keys=u2f_keys,
                ssh_key=text(u, "authorizedkeys") or text(u, "ssh_key"),
            )
        )
    return out


def parse_groups(root: Element) -> list[Group]:
    sys_el = root.find("system")
    if sys_el is None:
        return []
    out: list[Group] = []
    for g in children(sys_el, "group"):
        name = text(g, "name")
        if not name:
            continue
        privs = [e.text or "" for e in children(g, "priv") if e.text]
        members = [e.text or "" for e in children(g, "member") if e.text]
        out.append(
            Group(
                name=name,
                gid=text(g, "gid"),
                scope=text(g, "scope"),
                description=text(g, "description"),
                privs=privs,
                members=members,
            )
        )
    return out


def parse_authservers(root: Element) -> list[AuthServer]:
    sys_el = root.find("system")
    if sys_el is None:
        return []
    out: list[AuthServer] = []
    for a in children(sys_el, "authserver"):
        name = text(a, "name")
        if not name:
            continue
        out.append(
            AuthServer(
                name=name,
                type=text(a, "type"),
                host=text(a, "host"),
                port=text(a, "port") or text(a, "ldap_port") or text(a, "radius_auth_port"),
                ldap_bindpw=redact("ldap_bindpw", text(a, "ldap_bindpw")),
                radius_secret=redact("radius_secret", text(a, "radius_secret")),
                ldap_binddn=text(a, "ldap_binddn"),
                ldap_basedn=text(a, "ldap_basedn"),
                ldap_scope=text(a, "ldap_scope"),
                ldap_authcn=text(a, "ldap_authcn"),
            )
        )
    return out
