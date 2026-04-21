"""Tests for the structured-view endpoints:

- ``GET /api/backups/{id}/parsed``
- ``GET /api/backups/diff/pair/parsed``

Both exercise the encrypted, plain, and gzipped paths; both assert
audit entries land for decrypted reads. Contract: plaintext XML
never leaves the server untouched — it's parsed, redacted, and
serialized as the structured Pydantic model.
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pfsense_shared.crypto import Crypto

from .conftest import count_audit_entries

# --------- GET /api/backups/{id}/parsed -------------------------------


async def test_parsed_plain_backup_returns_structured_config(
    client: AsyncClient, seed_plain_backup: int
) -> None:
    r = await client.get(f"/api/backups/{seed_plain_backup}/parsed")
    assert r.status_code == 200, r.text
    body = r.json()
    # v0.22.0 wrapped the response as {config, positions}.
    cfg = body["config"]
    assert cfg["config_version"] == "21.9"
    assert cfg["system"]["hostname"] == "gw-test"
    assert cfg["system"]["domain"] == "lan.example"
    assert len(cfg["firewall_rules"]) == 1
    assert cfg["firewall_rules"][0]["type"] == "pass"
    assert cfg["firewall_rules"][0]["descr"] == "allow lan"
    # Positions map carries at least the singleton + rule anchors
    # the viewer's tab-switch sync relies on.
    pos = body["positions"]
    assert "section-system" in pos
    assert "field-system-hostname" in pos
    # Firewall rule tracker is "1" in the seeded fixture; the
    # position anchor uses the parser's synthesized key
    # (``tracker:1``) sanitised to ``tracker_1`` so it matches the
    # ``rowAnchorId("rule", r.key)`` emission on the frontend.
    assert "xref-rule-tracker_1" in pos


async def test_parsed_missing_backup_returns_404(client: AsyncClient) -> None:
    r = await client.get("/api/backups/9999/parsed")
    assert r.status_code == 404


async def test_parsed_gzipped_backup_is_decompressed(
    client: AsyncClient, seed_compressed_plain_backup: int
) -> None:
    r = await client.get(f"/api/backups/{seed_compressed_plain_backup}/parsed")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["config"]["system"]["hostname"] == "gw-test"


async def test_parsed_plain_backup_does_not_audit_as_decrypted(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    seed_plain_backup: int,
) -> None:
    """Plain backups don't need decryption — no ``view_decrypted`` row."""
    _, session_factory, _ = app_and_session
    r = await client.get(f"/api/backups/{seed_plain_backup}/parsed")
    assert r.status_code == 200
    count = await count_audit_entries(session_factory, "view_decrypted", "backup")
    assert count == 0


async def test_parsed_encrypted_backup_decrypts_and_audits(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    seed_encrypted_backup: tuple[int, str],
) -> None:
    _, session_factory, _ = app_and_session
    backup_id, _ = seed_encrypted_backup

    r = await client.get(f"/api/backups/{backup_id}/parsed")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["config"]["system"]["hostname"] == "gw-test"

    count = await count_audit_entries(
        session_factory, action="view_decrypted", resource="backup"
    )
    assert count == 1


# --------- GET /api/backups/diff/pair/parsed --------------------------


async def test_diff_pair_parsed_identical_backups_reports_no_changes(
    client: AsyncClient, seed_plain_backup: int
) -> None:
    # Diff a backup against itself — every section should be empty.
    r = await client.get(
        f"/api/backups/diff/pair/parsed?a={seed_plain_backup}&b={seed_plain_backup}"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    for section in ("system", "firewall_rules", "aliases"):
        s = body[section]
        assert s["added"] == []
        assert s["removed"] == []
        assert s["modified"] == []


async def test_diff_pair_parsed_detects_semantic_change(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    tmp_path,
    seed_plain_backup: int,
) -> None:
    """Seed a second backup with a different hostname + an extra firewall
    rule; diff should surface both."""
    from .conftest import _seed_backup_row

    _, session_factory, _ = app_and_session
    new_xml = b"""<?xml version="1.0"?>
<pfsense>
  <version>21.9</version>
  <system>
    <hostname>gw-test-2</hostname>
    <domain>lan.example</domain>
    <timezone>UTC</timezone>
  </system>
  <filter>
    <rule>
      <tracker>1</tracker>
      <type>pass</type>
      <interface>lan</interface>
      <descr>allow lan</descr>
    </rule>
    <rule>
      <tracker>2</tracker>
      <type>block</type>
      <interface>wan</interface>
      <descr>deny wan</descr>
    </rule>
  </filter>
</pfsense>
"""
    path = tmp_path / "daily_gw-test_2026-later.xml"
    path.write_bytes(new_xml)
    # reuse the existing instance id (= 1 — only seeded one)
    second = await _seed_backup_row(
        session_factory, instance_id=1, path=path, encrypted=False
    )

    r = await client.get(
        f"/api/backups/diff/pair/parsed?a={seed_plain_backup}&b={second.id}"
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # Hostname changed
    system_changes = [m for m in body["system"]["modified"] if m["key"] == "system"]
    assert len(system_changes) == 1
    fields = [c["field"] for c in system_changes[0]["changes"]]
    assert "hostname" in fields

    # New firewall rule surfaced as added
    added = body["firewall_rules"]["added"]
    assert len(added) == 1
    assert added[0]["tracker"] == "2"
    assert added[0]["descr"] == "deny wan"


async def test_diff_pair_parsed_encrypted_audits_once(
    client: AsyncClient,
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    seed_encrypted_backup: tuple[int, str],
) -> None:
    _, session_factory, _ = app_and_session
    backup_id, _ = seed_encrypted_backup
    r = await client.get(
        f"/api/backups/diff/pair/parsed?a={backup_id}&b={backup_id}"
    )
    assert r.status_code == 200, r.text
    # Exactly one audit entry on the diff resource even though both sides
    # needed decryption.
    count = await count_audit_entries(
        session_factory, action="view_decrypted", resource="backup_diff"
    )
    assert count == 1


async def test_diff_pair_parsed_missing_backup_returns_404(
    client: AsyncClient, seed_plain_backup: int
) -> None:
    r = await client.get(
        f"/api/backups/diff/pair/parsed?a={seed_plain_backup}&b=9999"
    )
    assert r.status_code == 404


# --------- no-auth path -----------------------------------------------


async def test_parsed_requires_authenticated_user(
    app_and_session: tuple[FastAPI, async_sessionmaker[AsyncSession], Crypto],
    seed_plain_backup: int,
) -> None:
    """Dropping the auth override → 401 (the real dependency reads the
    session cookie, which isn't set in tests)."""
    from httpx import ASGITransport, AsyncClient

    from web.dependencies import get_current_user

    app, _, _ = app_and_session
    # Restore real get_current_user → exercises the 401 path
    app.dependency_overrides.pop(get_current_user, None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get(f"/api/backups/{seed_plain_backup}/parsed")
    assert r.status_code == 401
