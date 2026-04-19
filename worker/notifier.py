"""Multi-channel notification dispatcher.

Routes each enabled Notification row to a kind-specific handler
(Discord, Home Assistant, Ntfy, Healthchecks) or falls back to the
generic webhook path. Supports per-instance scope filtering and
Healthchecks /start pings at run kickoff.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from pfsense_shared.models import Instance, Notification

from .prometheus_metrics import PrometheusMetrics

log = logging.getLogger(__name__)


class Notifier:
    """Notification dispatcher. Session is supplied per-call so it stays thread-local."""

    # Discord caps webhook `content` at 2000 chars. Keep a safety margin.
    _DISCORD_CONTENT_MAX = 1997  # 2000 - "..."

    def __init__(self, metrics: PrometheusMetrics, hostname: str) -> None:
        self._metrics = metrics
        self._hostname = hostname

    # -------------------------------------------------------------- #
    # public entry points
    # -------------------------------------------------------------- #

    def send(
        self,
        session: Session,
        *,
        is_success: bool,
        details: str,
        failed_instances: list[str] | None = None,
        succeeded_instances: list[str] | None = None,
    ) -> None:
        """Fire one terminal notification per enabled row.

        Per-instance scope filters (``instance_ids_json``) are evaluated
        per row: scoped rows only fire when one of the scoped instances
        actually ran, and the message / Healthchecks ping path reflect
        the scoped subset rather than the aggregate run outcome.
        """
        failed_instances = failed_instances or []
        succeeded_instances = succeeded_instances or []

        webhooks = (
            session.execute(select(Notification).where(Notification.enabled.is_(True)))
            .scalars()
            .all()
        )
        name_to_id = self._name_to_id_map(session)

        for hook in webhooks:
            scope = self._resolve_scope(
                hook, failed_instances, succeeded_instances, name_to_id,
                aggregate_is_success=is_success, aggregate_details=details,
            )
            if scope is None:
                continue
            effective_success, scoped_failed, scoped_details = scope
            if not self._should_send(hook.trigger, effective_success):
                continue
            status_label = "SUCCESS" if effective_success else "FAILURE"
            message = self._format_message(
                hook,
                status=status_label,
                details=scoped_details,
                failed_instances=scoped_failed,
            )
            # H8: one broken webhook must not silence the rest.
            try:
                self._dispatch(hook, message, is_success=effective_success)
            except Exception as exc:
                log.error("Webhook %s failed; continuing: %s", hook.name, exc)

    def ping_starts(self, session: Session) -> None:
        """Fire ``/start`` pings for all enabled Healthchecks rows.

        Called at the top of a backup run so Healthchecks can compute
        run duration between ``/start`` and the terminal ping. Per-instance
        filters apply: a scoped row only pings if at least one of its
        instances is enabled in this cycle.
        """
        rows = (
            session.execute(
                select(Notification).where(
                    Notification.enabled.is_(True),
                    Notification.kind == "healthchecks",
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return
        enabled_ids = {
            iid
            for (iid,) in session.execute(
                select(Instance.id).where(Instance.enabled.is_(True))
            ).all()
        }
        message = (
            "Backup run started\n"
            f"Host: {self._hostname}\n"
            f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        for hook in rows:
            if hook.instance_ids_json:
                try:
                    scoped = set(json.loads(hook.instance_ids_json))
                except (TypeError, ValueError):
                    continue
                if not (scoped & enabled_ids):
                    continue
            try:
                self._send_healthchecks(hook, message, is_success=True, is_start=True)
            except Exception as exc:
                log.warning("Healthchecks /start ping for %s failed: %s", hook.name, exc)

    def send_test(self, session: Session, notification_id: int) -> tuple[bool, str]:
        """Send a test message to a single configured notification."""
        hook = session.get(Notification, notification_id)
        if hook is None:
            return False, f"Notification {notification_id} not found"
        msg = self._format_message(
            hook,
            status="TEST",
            details="This is a test notification from pfsense-backups.",
            failed_instances=[],
        )
        try:
            # Test sends as a "success" for Healthchecks so the check
            # turns green rather than red; a red test would look like
            # a real failure on the user's dashboard.
            self._dispatch(hook, msg, is_success=True)
            return True, "sent"
        except Exception as exc:
            return False, str(exc)

    # -------------------------------------------------------------- #
    # internals
    # -------------------------------------------------------------- #

    @staticmethod
    def _should_send(trigger: str, is_success: bool) -> bool:
        t = trigger.lower()
        if t == "always":
            return True
        return (t == "success" and is_success) or (t == "failure" and not is_success)

    @staticmethod
    def _name_to_id_map(session: Session) -> dict[str, int]:
        rows = session.execute(select(Instance.id, Instance.name)).all()
        return {name: iid for iid, name in rows}

    @staticmethod
    def _resolve_scope(
        hook: Notification,
        failed_instances: list[str],
        succeeded_instances: list[str],
        name_to_id: dict[str, int],
        *,
        aggregate_is_success: bool,
        aggregate_details: str,
    ) -> tuple[bool, list[str], str] | None:
        """Compute (effective_success, scoped_failed, details) for a row, or None to skip."""
        if not hook.instance_ids_json:
            return aggregate_is_success, failed_instances, aggregate_details
        try:
            allowed_ids = set(json.loads(hook.instance_ids_json))
        except (TypeError, ValueError):
            return None
        if not allowed_ids:
            return aggregate_is_success, failed_instances, aggregate_details
        failed_in_scope = [n for n in failed_instances if name_to_id.get(n) in allowed_ids]
        ok_in_scope = [n for n in succeeded_instances if name_to_id.get(n) in allowed_ids]
        if not failed_in_scope and not ok_in_scope:
            return None
        scoped_success = not failed_in_scope
        total = len(failed_in_scope) + len(ok_in_scope)
        details = (
            f"All {total} scoped instance(s) backed up successfully"
            if scoped_success
            else f"Scoped backup failures ({len(failed_in_scope)}/{total} failed)"
        )
        return scoped_success, failed_in_scope, details

    def _format_message(
        self,
        hook: Notification,
        *,
        status: str,
        details: str,
        failed_instances: list[str],
    ) -> str:
        msg = hook.message_format.format(status=status, details=details)
        if hook.include_instance_details and failed_instances:
            msg += f"\nFailed instances: {', '.join(failed_instances)}"
        msg += f"\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        msg += f"\nHost: {self._hostname}"
        return msg

    @staticmethod
    def _config(hook: Notification) -> dict[str, Any]:
        if not hook.config_json:
            return {}
        try:
            parsed = json.loads(hook.config_json)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _dispatch(self, hook: Notification, message: str, *, is_success: bool) -> None:
        kind = hook.kind or "webhook"
        if kind == "discord":
            self._send_discord(hook, message)
        elif kind == "home_assistant":
            self._send_home_assistant(hook, message, is_success=is_success)
        elif kind == "ntfy":
            self._send_ntfy(hook, message, is_success=is_success)
        elif kind == "healthchecks":
            self._send_healthchecks(hook, message, is_success=is_success)
        else:
            self._send_webhook(hook, message)

    def _post(
        self,
        hook: Notification,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Centralized POST + metrics bookkeeping."""
        try:
            if json_body is not None:
                resp = requests.post(
                    url, json=json_body, headers=headers, timeout=hook.timeout_seconds
                )
            elif data is not None:
                resp = requests.post(
                    url, data=data, headers=headers, timeout=hook.timeout_seconds
                )
            else:
                resp = requests.post(url, headers=headers, timeout=hook.timeout_seconds)
            resp.raise_for_status()
            log.info("Notification sent to %s", hook.name)
            self._metrics.record_notification(hook.name, True)
        except Exception as exc:
            log.error("Notification %s failed: %s", hook.name, exc)
            self._metrics.record_notification(hook.name, False)
            raise

    # ---------- per-kind handlers ---------- #

    def _send_discord(self, hook: Notification, message: str) -> None:
        content = message
        if len(content) > self._DISCORD_CONTENT_MAX:
            log.warning(
                "Truncating Discord content for %s from %d to %d chars",
                hook.name,
                len(content),
                self._DISCORD_CONTENT_MAX,
            )
            content = content[: self._DISCORD_CONTENT_MAX] + "..."
        self._post(
            hook,
            hook.url,
            json_body={"content": content},
            headers={"Content-Type": "application/json"},
        )

    def _send_home_assistant(
        self, hook: Notification, message: str, *, is_success: bool
    ) -> None:
        cfg = self._config(hook)
        token = str(cfg.get("access_token") or "")
        mode = str(cfg.get("mode") or "notify")
        title = str(cfg.get("title") or "pfSense Backup")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if mode == "webhook":
            body: dict[str, Any] = {
                "message": message,
                "title": title,
                "status": "success" if is_success else "failure",
                "host": self._hostname,
            }
        else:
            body = {"message": message, "title": title}
        self._post(hook, hook.url, json_body=body, headers=headers)

    def _send_ntfy(
        self, hook: Notification, message: str, *, is_success: bool
    ) -> None:
        cfg = self._config(hook)
        headers: dict[str, str] = {"Title": "pfSense Backup"}
        priority = cfg.get("priority")
        if priority:
            headers["Priority"] = str(priority)
        elif not is_success:
            # Bump failure pings above the default so the user's phone
            # actually wakes up; success pings stay silent by default.
            headers["Priority"] = "4"
        tags = cfg.get("tags")
        if isinstance(tags, list) and tags:
            headers["Tags"] = ",".join(str(t) for t in tags)
        token = cfg.get("auth_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._post(hook, hook.url, data=message.encode("utf-8"), headers=headers)

    def _send_healthchecks(
        self,
        hook: Notification,
        message: str,
        *,
        is_success: bool,
        is_start: bool = False,
    ) -> None:
        base = hook.url.rstrip("/")
        if is_start:
            url = f"{base}/start"
        elif is_success:
            url = base
        else:
            url = f"{base}/fail"
        # Healthchecks truncates bodies; keep the POST small to stay
        # within their 10KB-ish soft limit.
        body = message.encode("utf-8")[:8192]
        self._post(
            hook,
            url,
            data=body,
            headers={"User-Agent": "pfSense-Backup-Manager"},
        )

    def _send_webhook(self, hook: Notification, message: str) -> None:
        url = hook.url
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if hook.headers_json:
            # M2: URL is stored as-is; don't expandvars. Headers commonly
            # carry `Authorization: Bearer ${TOKEN}` and benefit from
            # per-call env expansion.
            for k, v in json.loads(hook.headers_json).items():
                headers[k] = os.path.expandvars(str(v))

        payload: dict[str, Any] | None
        is_discord_url = "discord.com/api/webhooks" in url.lower()

        if hook.payload_template_json:
            tmpl = json.loads(hook.payload_template_json)
            payload = {
                k: (v.format(message=message) if isinstance(v, str) else v)
                for k, v in tmpl.items()
            }
        elif is_discord_url:
            payload = {"content": message}
        else:
            payload = {"text": message, "timestamp": datetime.now().isoformat()}

        # M3: Discord caps payload.content at 2000 chars.
        if payload is not None and is_discord_url:
            content = payload.get("content")
            if isinstance(content, str) and len(content) > self._DISCORD_CONTENT_MAX:
                payload["content"] = content[: self._DISCORD_CONTENT_MAX] + "..."
                log.warning(
                    "Truncated Discord content for %s from %d to %d chars",
                    hook.name,
                    len(content),
                    self._DISCORD_CONTENT_MAX + 3,
                )

        if payload is None:
            self._post(
                hook, url, headers={"User-Agent": "pfSense-Backup-Manager"}
            )
        else:
            self._post(hook, url, json_body=payload, headers=headers)
