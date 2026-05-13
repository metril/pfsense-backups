"""Parses OpenVPN (servers, clients, client-specific overrides) and IPsec
(phase1 tunnels, phase2 SAs, pre-shared keys).

All cryptographic material is redacted via the shared engine:
- ``<tls>``, ``<tls_auth>`` (TLS auth keys)
- ``<shared_key>`` (static-key mode)
- ``<presharedkey>``, ``<pskey>``, ``<psk>`` (IPsec PSKs)
- ``<password>`` anywhere (routes through the redaction suffix rule)
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact

from ._helpers import bool_flag, children, text

# ---------- OpenVPN -------------------------------------------------------


class OpenVpnServer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vpnid: str
    description: str | None = None
    mode: str | None = None  # server_user | server_tls_user | p2p_shared_key | ...
    protocol: str | None = None
    interface: str | None = None
    local_port: str | None = None
    tunnel_network: str | None = None
    tunnel_networkv6: str | None = None
    remote_network: str | None = None
    remote_networkv6: str | None = None
    local_network: str | None = None
    local_networkv6: str | None = None
    dev_mode: str | None = None  # tun | tap
    topology: str | None = None
    crypto: str | None = None  # data cipher
    digest: str | None = None
    caref: str | None = None
    certref: str | None = None
    authmode: list[str] = []
    # v0.42.0 — advanced server fields. ``push_options`` is the raw
    # multi-line text pushed to every client; ``custom_options`` are
    # raw OpenVPN directives appended verbatim to the server config.
    # Both can carry security-sensitive routing changes that need to
    # be visible in diffs.
    push_options: str | None = None
    custom_options: str | None = None
    comp_lzo: str | None = None  # adaptive | yes | no | empty
    verify_x509_name: str | None = None
    x509_alt_name: str | None = None
    fragment: str | None = None
    mtu_test: bool = False
    tunnel_mtu: str | None = None
    data_ciphers: str | None = None
    data_ciphers_fallback: str | None = None
    # Redacted
    shared_key: str | None = None
    tls: str | None = None


class OpenVpnClient(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vpnid: str
    description: str | None = None
    mode: str | None = None
    protocol: str | None = None
    interface: str | None = None
    server_addr: str | None = None
    server_port: str | None = None
    tunnel_network: str | None = None
    dev_mode: str | None = None
    crypto: str | None = None
    digest: str | None = None
    caref: str | None = None
    certref: str | None = None
    # v0.42.0 — see OpenVpnServer.
    custom_options: str | None = None
    comp_lzo: str | None = None
    fragment: str | None = None
    tunnel_mtu: str | None = None
    data_ciphers: str | None = None
    data_ciphers_fallback: str | None = None
    # Client auth user/pass — username is not secret, password is.
    username: str | None = None
    password: str | None = None  # redacted
    # Auth-user-pass-verify static creds blob — redacted as a whole.
    auth_user_pass: str | None = None
    # Redacted
    shared_key: str | None = None
    tls: str | None = None


class OpenVpnCsc(BaseModel):
    """OpenVPN client-specific override (push routes to a named CN)."""

    model_config = ConfigDict(extra="forbid")

    common_name: str
    description: str | None = None
    disable: bool = False
    block: bool = False
    server_list: list[str] = []
    tunnel_network: str | None = None
    local_network: str | None = None
    remote_network: str | None = None
    push_reset: bool = False
    dns_server1: str | None = None
    ntp_server1: str | None = None


# ---------- IPsec --------------------------------------------------------


class IpsecPhase1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # ``ikeid`` is the stable pfSense-assigned id that phase2 entries
    # reference (<ikeid> inside phase2).
    ikeid: str
    iketype: str | None = None  # ikev1 | ikev2 | auto
    interface: str | None = None
    remote_gateway: str | None = None
    protocol: str | None = None  # inet | inet6
    descr: str | None = None
    disabled: bool = False
    # Authentication
    authentication_method: str | None = None  # psk | cert | hybrid...
    myid_type: str | None = None
    myid_data: str | None = None
    peerid_type: str | None = None
    peerid_data: str | None = None
    # v0.42.0 — DPD + lifetimes + mobike + NAT-T + main/aggressive
    # mode. Critical for tunnel-stability reviews; previously dropped.
    mode: str | None = None  # main | aggressive
    nat_traversal: str | None = None  # on | off | force
    mobike: str | None = None  # on | off
    dpd_action: str | None = None  # restart | clear | none
    dpd_delay: str | None = None  # seconds
    dpd_maxfail: str | None = None
    lifetime: str | None = None  # seconds
    reauth_time: str | None = None
    gw_duplicates: bool = False
    # Redacted
    pre_shared_key: str | None = None
    # Encryption set (flattened for diff legibility; each entry is
    # "enc-alg/keylen/hash/dh" like the pfSense UI renders).
    encryption_set: list[str] = []


class IpsecPhase2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uniqid: str
    ikeid: str | None = None  # back-ref to phase1
    descr: str | None = None
    disabled: bool = False
    mode: str | None = None  # tunnel | transport | vti
    protocol: str | None = None
    # Local / remote selectors
    local_type: str | None = None  # "network" | "address" | ...
    local_address: str | None = None
    local_netbits: str | None = None
    remote_type: str | None = None
    remote_address: str | None = None
    remote_netbits: str | None = None
    encryption_set: list[str] = []
    # v0.42.0 — lifetime/keepalive/pfsgroup + VTI tunnel-interface
    # addresses. VTI phase2 entries store the tunnel interface's local
    # + remote inner addresses (the "interface IPs" the tunnel
    # presents), which are needed to actually understand what a VTI
    # tunnel is doing.
    lifetime: str | None = None
    keepalive: str | None = None
    pfsgroup: str | None = None
    mode_vti_addr: str | None = None
    mode_vti_remote_addr: str | None = None


class IpsecMobileClient(BaseModel):
    """``<ipsec><mobileclients>`` — IKEv2/IKEv1 road-warrior config
    block. Single instance (not a list)."""

    model_config = ConfigDict(extra="forbid")

    enable: bool = False
    user_source: str | None = None
    group_source: str | None = None
    pool_address: str | None = None
    pool_netbits: str | None = None
    dns_address: str | None = None
    wins_address: str | None = None
    login_banner: str | None = None


class IpsecPskEntry(BaseModel):
    """A standalone PSK table entry (not tied to a phase1)."""

    model_config = ConfigDict(extra="forbid")

    # Stable key: ident + ident_type combo.
    key: str
    ident_type: str | None = None
    ident: str | None = None
    pre_shared_key: str | None = None  # redacted


def _encryption_set(el: Element) -> list[str]:
    """Flatten ``<encryption>`` entries into readable strings.

    phase1 and phase2 both use this shape:
    ``<encryption><item><encryption-algorithm><name>aes</name>
    <keylen>256</keylen></encryption-algorithm><hash-algorithm>sha256
    </hash-algorithm><dhgroup>14</dhgroup></item></encryption>``
    """
    enc = el.find("encryption")
    if enc is None:
        return []
    out: list[str] = []
    for item in children(enc, "item"):
        ea = item.find("encryption-algorithm")
        parts: list[str] = []
        if ea is not None:
            name = text(ea, "name")
            keylen = text(ea, "keylen")
            if name and keylen:
                parts.append(f"{name}-{keylen}")
            elif name:
                parts.append(name)
        hsh = text(item, "hash-algorithm")
        if hsh:
            parts.append(hsh)
        dh = text(item, "dhgroup") or text(item, "pfsgroup")
        if dh:
            parts.append(f"dh{dh}")
        if parts:
            out.append("/".join(parts))
    return out


def parse_openvpn(
    root: Element,
) -> tuple[list[OpenVpnServer], list[OpenVpnClient], list[OpenVpnCsc]]:
    el = root.find("openvpn")
    if el is None:
        return [], [], []

    servers: list[OpenVpnServer] = []
    for s in children(el, "openvpn-server"):
        vpnid = text(s, "vpnid")
        if not vpnid:
            continue
        authmode_raw = text(s, "authmode") or ""
        servers.append(
            OpenVpnServer(
                vpnid=vpnid,
                description=text(s, "description"),
                mode=text(s, "mode"),
                protocol=text(s, "protocol"),
                interface=text(s, "interface"),
                local_port=text(s, "local_port"),
                tunnel_network=text(s, "tunnel_network"),
                tunnel_networkv6=text(s, "tunnel_networkv6"),
                remote_network=text(s, "remote_network"),
                remote_networkv6=text(s, "remote_networkv6"),
                local_network=text(s, "local_network"),
                local_networkv6=text(s, "local_networkv6"),
                dev_mode=text(s, "dev_mode"),
                topology=text(s, "topology"),
                crypto=text(s, "data_ciphers_fallback") or text(s, "crypto"),
                digest=text(s, "digest"),
                caref=text(s, "caref"),
                certref=text(s, "certref"),
                authmode=[x for x in authmode_raw.split(",") if x],
                push_options=text(s, "push_options"),
                custom_options=text(s, "custom_options"),
                comp_lzo=text(s, "compression") or text(s, "comp_lzo"),
                verify_x509_name=text(s, "verify_x509_name"),
                x509_alt_name=text(s, "x509_alt_name"),
                fragment=text(s, "fragment"),
                mtu_test=bool_flag(s, "mtu_test"),
                tunnel_mtu=text(s, "tunnel_mtu"),
                data_ciphers=text(s, "data_ciphers"),
                data_ciphers_fallback=text(s, "data_ciphers_fallback"),
                shared_key=redact("shared_key", text(s, "shared_key")),
                # pfSense 2.4 stored the HMAC firewall key under
                # <tls_auth>; 2.5+ collapsed it into <tls>. Read both
                # so older backups don't silently drop the field.
                tls=redact("tls", text(s, "tls") or text(s, "tls_auth")),
            )
        )

    clients: list[OpenVpnClient] = []
    for c in children(el, "openvpn-client"):
        vpnid = text(c, "vpnid")
        if not vpnid:
            continue
        clients.append(
            OpenVpnClient(
                vpnid=vpnid,
                description=text(c, "description"),
                mode=text(c, "mode"),
                protocol=text(c, "protocol"),
                interface=text(c, "interface"),
                server_addr=text(c, "server_addr"),
                server_port=text(c, "server_port"),
                tunnel_network=text(c, "tunnel_network"),
                dev_mode=text(c, "dev_mode"),
                crypto=text(c, "data_ciphers_fallback") or text(c, "crypto"),
                digest=text(c, "digest"),
                caref=text(c, "caref"),
                certref=text(c, "certref"),
                custom_options=text(c, "custom_options"),
                comp_lzo=text(c, "compression") or text(c, "comp_lzo"),
                fragment=text(c, "fragment"),
                tunnel_mtu=text(c, "tunnel_mtu"),
                data_ciphers=text(c, "data_ciphers"),
                data_ciphers_fallback=text(c, "data_ciphers_fallback"),
                # Username is identity (not a secret); password +
                # auth_user_pass blob redact via the global rules.
                username=text(c, "auth_user") or text(c, "username"),
                password=redact("password", text(c, "auth_pass") or text(c, "password")),
                auth_user_pass=redact("auth_user_pass", text(c, "auth_user_pass")),
                shared_key=redact("shared_key", text(c, "shared_key")),
                tls=redact("tls", text(c, "tls") or text(c, "tls_auth")),
            )
        )

    cscs: list[OpenVpnCsc] = []
    for cso in children(el, "openvpn-csc"):
        cn = text(cso, "common_name")
        if not cn:
            continue
        server_list_raw = text(cso, "server_list") or ""
        cscs.append(
            OpenVpnCsc(
                common_name=cn,
                description=text(cso, "description"),
                disable=bool_flag(cso, "disable"),
                block=bool_flag(cso, "block"),
                server_list=[x for x in server_list_raw.split(",") if x],
                tunnel_network=text(cso, "tunnel_network"),
                local_network=text(cso, "local_network"),
                remote_network=text(cso, "remote_network"),
                push_reset=bool_flag(cso, "push_reset"),
                dns_server1=text(cso, "dns_server1"),
                ntp_server1=text(cso, "ntp_server1"),
            )
        )
    return servers, clients, cscs


def parse_ipsec(
    root: Element,
) -> tuple[
    list[IpsecPhase1],
    list[IpsecPhase2],
    list[IpsecPskEntry],
    IpsecMobileClient | None,
]:
    el = root.find("ipsec")
    if el is None:
        return [], [], [], None

    phase1s: list[IpsecPhase1] = []
    for p in children(el, "phase1"):
        ikeid = text(p, "ikeid")
        if not ikeid:
            continue
        phase1s.append(
            IpsecPhase1(
                ikeid=ikeid,
                iketype=text(p, "iketype"),
                interface=text(p, "interface"),
                remote_gateway=text(p, "remote-gateway"),
                protocol=text(p, "protocol"),
                descr=text(p, "descr"),
                disabled=bool_flag(p, "disabled"),
                authentication_method=text(p, "authentication_method"),
                myid_type=text(p, "myid_type"),
                myid_data=text(p, "myid_data"),
                peerid_type=text(p, "peerid_type"),
                peerid_data=text(p, "peerid_data"),
                mode=text(p, "mode"),
                nat_traversal=text(p, "nat_traversal"),
                mobike=text(p, "mobike"),
                dpd_action=text(p, "dpd_action"),
                dpd_delay=text(p, "dpd_delay"),
                dpd_maxfail=text(p, "dpd_maxfail"),
                lifetime=text(p, "lifetime"),
                reauth_time=text(p, "reauth_time"),
                gw_duplicates=bool_flag(p, "gw_duplicates"),
                pre_shared_key=redact("pre_shared_key", text(p, "pre-shared-key")),
                encryption_set=_encryption_set(p),
            )
        )

    phase2s: list[IpsecPhase2] = []
    for p in children(el, "phase2"):
        uniqid = text(p, "uniqid")
        if not uniqid:
            continue
        local = p.find("localid")
        remote = p.find("remoteid")
        phase2s.append(
            IpsecPhase2(
                uniqid=uniqid,
                ikeid=text(p, "ikeid"),
                descr=text(p, "descr"),
                disabled=bool_flag(p, "disabled"),
                mode=text(p, "mode"),
                protocol=text(p, "protocol"),
                local_type=text(local, "type") if local is not None else None,
                local_address=text(local, "address") if local is not None else None,
                local_netbits=text(local, "netbits") if local is not None else None,
                remote_type=text(remote, "type") if remote is not None else None,
                remote_address=text(remote, "address") if remote is not None else None,
                remote_netbits=text(remote, "netbits") if remote is not None else None,
                encryption_set=_encryption_set(p),
                lifetime=text(p, "lifetime"),
                keepalive=text(p, "pinghost") or text(p, "keepalive"),
                pfsgroup=text(p, "pfsgroup"),
                mode_vti_addr=text(p, "mode_vti_addr"),
                mode_vti_remote_addr=text(p, "mode_vti_remote_addr"),
            )
        )

    psks: list[IpsecPskEntry] = []
    for entry in children(el, "mobilekey"):
        ident = text(entry, "ident")
        ident_type = text(entry, "ident_type")
        if not ident:
            continue
        psks.append(
            IpsecPskEntry(
                key=f"{ident_type or '?'}:{ident}",
                ident_type=ident_type,
                ident=ident,
                pre_shared_key=redact(
                    "pre_shared_key", text(entry, "pre-shared-key")
                ),
            )
        )

    # Mobile-clients block — single instance under <ipsec><mobileclients>.
    mob_el = el.find("mobileclients")
    mobile_clients: IpsecMobileClient | None = None
    if mob_el is not None:
        mobile_clients = IpsecMobileClient(
            enable=bool_flag(mob_el, "enable"),
            user_source=text(mob_el, "user_source"),
            group_source=text(mob_el, "group_source"),
            pool_address=text(mob_el, "pool_address"),
            pool_netbits=text(mob_el, "pool_netbits"),
            dns_address=text(mob_el, "dns_address"),
            wins_address=text(mob_el, "wins_address"),
            login_banner=text(mob_el, "login_banner"),
        )

    return phase1s, phase2s, psks, mobile_clients
