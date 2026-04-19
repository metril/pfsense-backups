"""Notification CRUD + test send.

Handles per-kind URL composition (Home Assistant and Ntfy compute their
final endpoint from ``config`` components) and Healthchecks
auto-provisioning (create/update/delete the upstream check via the
Healthchecks management API when ``config.provisioned`` is true).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from pfsense_shared.models import Job, Notification
from pfsense_shared.schemas import (
    NotificationCreate,
    NotificationRead,
    NotificationUpdate,
    SendTestNotificationCommand,
)

from ..dependencies import CurrentUser, DbSession, Ipc
from ..services import audit

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _to_read(row: Notification) -> NotificationRead:
    return NotificationRead.model_validate(
        {
            "id": row.id,
            "name": row.name,
            "kind": row.kind or "webhook",
            "url": row.url,
            "trigger": row.trigger,
            "enabled": row.enabled,
            "message_format": row.message_format,
            "include_instance_details": row.include_instance_details,
            "timeout_seconds": row.timeout_seconds,
            "headers": json.loads(row.headers_json) if row.headers_json else None,
            "payload_template": (
                json.loads(row.payload_template_json) if row.payload_template_json else None
            ),
            "config": _redact_config(
                json.loads(row.config_json) if row.config_json else None
            ),
            "instance_ids": (
                json.loads(row.instance_ids_json) if row.instance_ids_json else None
            ),
        }
    )


# Secret fields in config_json that must never leave the server in
# plaintext. The value is still stored server-side for dispatch.
_SECRET_CONFIG_KEYS = {"access_token", "auth_token", "api_key"}


def _redact_config(config: dict[str, Any] | None) -> dict[str, Any] | None:
    if not config:
        return None
    out: dict[str, Any] = {}
    for k, v in config.items():
        if k in _SECRET_CONFIG_KEYS and isinstance(v, str) and v:
            # Surface that a secret is present (so the UI can show
            # "••••••••" placeholder) without exposing its value.
            out[k] = "__set__"
        else:
            out[k] = v
    return out


def _compose_url(kind: str, config: dict[str, Any] | None, fallback_url: str) -> str:
    """Derive the dispatch URL from kind-specific config components.

    Home Assistant and Ntfy rows store their structured components in
    ``config`` for round-trip editability; the dispatcher still just
    POSTs to ``url``. Kinds that don't compose fall back to the user-
    supplied URL as-is.
    """
    if not config:
        return fallback_url
    if kind == "home_assistant":
        base = str(config.get("base_url") or "").rstrip("/")
        if not base:
            return fallback_url
        mode = config.get("mode") or "notify"
        if mode == "notify":
            service = str(config.get("service") or "")
            if service:
                return f"{base}/api/services/notify/{service.lstrip('/')}"
        elif mode == "webhook":
            webhook_id = str(config.get("webhook_id") or "")
            if webhook_id:
                return f"{base}/api/webhook/{webhook_id.lstrip('/')}"
        return fallback_url
    if kind == "ntfy":
        server = str(config.get("server_url") or "").rstrip("/")
        topic = str(config.get("topic") or "").strip("/")
        if server and topic:
            return f"{server}/{topic}"
        return fallback_url
    return fallback_url


def _merge_secrets(
    old_config: dict[str, Any] | None, new_config: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Re-hydrate secrets the client never received (the UI sends "__set__").

    _redact_config strips real secrets out of GET responses; on save the
    UI echoes "__set__" back for any field it didn't change, and we
    restore the previously stored value from ``old_config`` here. A
    brand-new non-empty string from the client is always trusted.
    """
    if new_config is None:
        return None
    old = old_config or {}
    merged = dict(new_config)
    for key in _SECRET_CONFIG_KEYS:
        if key in merged and merged[key] == "__set__":
            if key in old:
                merged[key] = old[key]
            else:
                merged.pop(key)
    return merged


async def _healthchecks_create(
    server_url: str, api_key: str, body: dict[str, Any]
) -> dict[str, Any]:
    url = f"{server_url.rstrip('/')}/api/v3/checks/"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=body, headers={"X-Api-Key": api_key})
    if resp.status_code not in (200, 201):
        raise HTTPException(
            400,
            f"Healthchecks API returned {resp.status_code}: {resp.text[:200]}",
        )
    return resp.json()


async def _healthchecks_update(
    server_url: str, api_key: str, uuid: str, body: dict[str, Any]
) -> None:
    url = f"{server_url.rstrip('/')}/api/v3/checks/{uuid}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=body, headers={"X-Api-Key": api_key})
    if resp.status_code not in (200, 201):
        log.warning(
            "Healthchecks update for %s failed (%d): %s",
            uuid, resp.status_code, resp.text[:200],
        )


async def _healthchecks_delete(server_url: str, api_key: str, uuid: str) -> None:
    url = f"{server_url.rstrip('/')}/api/v3/checks/{uuid}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.delete(url, headers={"X-Api-Key": api_key})
        if resp.status_code not in (200, 404):
            log.warning(
                "Healthchecks delete for %s failed (%d): %s",
                uuid, resp.status_code, resp.text[:200],
            )
    except Exception as exc:
        # Best-effort: a broken Healthchecks endpoint must not block
        # the local delete.
        log.warning("Healthchecks delete for %s raised: %s", uuid, exc)


def _provision_body(config: dict[str, Any], name: str) -> dict[str, Any]:
    return {
        "name": name,
        "tags": "pfsense-backups",
        "timeout": int(config.get("expected_timeout") or 86400),
        "grace": int(config.get("grace") or 3600),
    }


async def _maybe_provision(
    config: dict[str, Any] | None, name: str
) -> tuple[str | None, dict[str, Any] | None]:
    """If config requests auto-provisioning, create the check upstream.

    Returns (ping_url, updated_config) — the caller persists both on
    the notification row. For manual or non-Healthchecks kinds, returns
    (None, config) unchanged.
    """
    if not config or not config.get("provisioned"):
        return None, config
    server_url = str(config.get("server_url") or "").rstrip("/")
    api_key = str(config.get("api_key") or "")
    if not server_url or not api_key:
        raise HTTPException(400, "auto-provision requires server_url and api_key")
    data = await _healthchecks_create(server_url, api_key, _provision_body(config, name))
    ping_url = str(data.get("ping_url") or "")
    uuid = str(data.get("uuid") or "")
    if not ping_url or not uuid:
        raise HTTPException(502, "Healthchecks API returned no ping_url/uuid")
    updated = dict(config)
    updated["uuid"] = uuid
    return ping_url, updated


@router.get("", response_model=list[NotificationRead])
async def list_notifications(db: DbSession) -> list[NotificationRead]:
    rows = (await db.scalars(select(Notification).order_by(Notification.name))).all()
    return [_to_read(r) for r in rows]


@router.post("", response_model=NotificationRead, status_code=status.HTTP_201_CREATED)
async def create_notification(
    payload: NotificationCreate, db: DbSession, user: CurrentUser
) -> NotificationRead:
    kind = payload.kind or "webhook"
    # Healthchecks fires on both success and failure; trigger=always is
    # the only coherent setting.
    trigger = "always" if kind == "healthchecks" else payload.trigger
    config = payload.config

    # Auto-provision upstream check first so we can persist the returned
    # ping URL into `url`.
    ping_url, config = await _maybe_provision(config, payload.name)
    final_url = ping_url or _compose_url(kind, config, payload.url)

    row = Notification(
        name=payload.name,
        kind=kind,
        url=final_url,
        trigger=trigger,
        enabled=payload.enabled,
        message_format=payload.message_format,
        include_instance_details=payload.include_instance_details,
        timeout_seconds=payload.timeout_seconds,
        headers_json=json.dumps(payload.headers) if payload.headers else None,
        payload_template_json=(
            json.dumps(payload.payload_template) if payload.payload_template else None
        ),
        config_json=json.dumps(config) if config else None,
        instance_ids_json=(
            json.dumps(payload.instance_ids) if payload.instance_ids else None
        ),
    )
    db.add(row)
    await db.flush()
    audit.record(
        db, actor_email=user["email"], action="create", resource="notification",
        resource_id=row.id, details={"name": row.name, "kind": kind},
    )
    await db.commit()
    return _to_read(row)


@router.put("/{notification_id}", response_model=NotificationRead)
async def update_notification(
    notification_id: int, payload: NotificationUpdate, db: DbSession, user: CurrentUser
) -> NotificationRead:
    row = await db.get(Notification, notification_id)
    if row is None:
        raise HTTPException(404, "notification not found")

    sent = payload.model_dump(exclude_unset=True)

    # Reject kind changes — different kinds expose different fields and
    # an in-place switch would leave config/url in an inconsistent state.
    if "kind" in sent and sent["kind"] != row.kind:
        raise HTTPException(
            400,
            "cannot change a notification's kind; delete and recreate instead",
        )

    changed: dict[str, Any] = {}

    # Merge incoming config with the existing row so __set__ placeholders
    # for secrets resolve to the previously stored value.
    old_config = json.loads(row.config_json) if row.config_json else None
    new_config: dict[str, Any] | None = old_config
    if "config" in sent:
        new_config = _merge_secrets(old_config, sent["config"])

    # For auto-provisioned Healthchecks rows, sync upstream changes.
    if row.kind == "healthchecks" and new_config and new_config.get("provisioned"):
        server_url = str(new_config.get("server_url") or "")
        api_key = str(new_config.get("api_key") or "")
        uuid = str(new_config.get("uuid") or "")
        new_name = sent.get("name", row.name)
        if server_url and api_key and uuid:
            await _healthchecks_update(
                server_url, api_key, uuid,
                _provision_body(new_config, new_name),
            )

    # Scalar fields.
    for field in (
        "name", "url", "trigger", "enabled", "message_format",
        "include_instance_details", "timeout_seconds",
    ):
        if field not in sent:
            continue
        val = sent[field]
        if val is None:
            continue
        if getattr(row, field) != val:
            setattr(row, field, val)
            changed[field] = val

    # Healthchecks trigger stays "always" regardless of what the client
    # sends.
    if row.kind == "healthchecks" and row.trigger != "always":
        row.trigger = "always"
        changed["trigger"] = "always"

    if "headers" in sent:
        row.headers_json = (
            json.dumps(sent["headers"]) if sent["headers"] else None
        )
        changed["headers"] = "<updated>"
    if "payload_template" in sent:
        row.payload_template_json = (
            json.dumps(sent["payload_template"]) if sent["payload_template"] else None
        )
        changed["payload_template"] = "<updated>"
    if "config" in sent:
        row.config_json = json.dumps(new_config) if new_config else None
        changed["config"] = "<updated>"
    if "instance_ids" in sent:
        row.instance_ids_json = (
            json.dumps(sent["instance_ids"]) if sent["instance_ids"] else None
        )
        changed["instance_ids"] = sent["instance_ids"] or []

    # Recompute dispatch URL from config for kinds that derive it.
    if row.kind in ("home_assistant", "ntfy") and (
        "config" in sent or "url" in sent
    ):
        row.url = _compose_url(row.kind, new_config, row.url)
        changed["url"] = row.url

    if changed:
        row.updated_at = datetime.now(UTC)
        audit.record(
            db, actor_email=user["email"], action="update", resource="notification",
            resource_id=row.id, details=changed,
        )
        await db.commit()
    return _to_read(row)


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: int, db: DbSession, user: CurrentUser
) -> None:
    row = await db.get(Notification, notification_id)
    if row is None:
        raise HTTPException(404, "notification not found")

    # Best-effort: tear down the upstream Healthchecks check so the
    # user's dashboard doesn't accumulate orphaned checks.
    if row.kind == "healthchecks" and row.config_json:
        try:
            cfg = json.loads(row.config_json)
        except (TypeError, ValueError):
            cfg = {}
        if cfg.get("provisioned"):
            server_url = str(cfg.get("server_url") or "")
            api_key = str(cfg.get("api_key") or "")
            uuid = str(cfg.get("uuid") or "")
            if server_url and api_key and uuid:
                await _healthchecks_delete(server_url, api_key, uuid)

    name = row.name
    await db.delete(row)
    audit.record(
        db, actor_email=user["email"], action="delete", resource="notification",
        resource_id=notification_id, details={"name": name},
    )
    await db.commit()


@router.post("/{notification_id}/test")
async def send_test(
    notification_id: int, db: DbSession, user: CurrentUser, ipc: Ipc
) -> dict[str, int]:
    if (await db.get(Notification, notification_id)) is None:
        raise HTTPException(404, "notification not found")
    job = Job(kind="test_notification", requested_by=user["email"])
    db.add(job)
    await db.flush()
    audit.record(
        db, actor_email=user["email"], action="trigger", resource="notification_test",
        resource_id=notification_id,
    )
    await db.commit()
    await ipc.send(
        SendTestNotificationCommand(notification_id=notification_id, job_id=job.id)
    )
    return {"job_id": job.id}
