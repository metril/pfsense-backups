"""Webhook notification dispatcher.

Reads Notification rows from the DB and sends webhook calls with configurable
payload templates, headers, and per-webhook trigger conditions.
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

from pfsense_shared.models import Notification

from .prometheus_metrics import PrometheusMetrics

log = logging.getLogger(__name__)


class Notifier:
    """Webhook dispatcher. Session is supplied per-call so it stays thread-local."""

    def __init__(self, metrics: PrometheusMetrics, hostname: str) -> None:
        self._metrics = metrics
        self._hostname = hostname

    def send(
        self,
        session: Session,
        *,
        is_success: bool,
        details: str,
        failed_instances: list[str] | None = None,
    ) -> None:
        status = "SUCCESS" if is_success else "FAILURE"
        webhooks = session.execute(
            select(Notification).where(Notification.enabled.is_(True))
        ).scalars().all()

        for hook in webhooks:
            if not self._should_send(hook.trigger, is_success):
                continue
            message = self._format_message(
                hook, status=status, details=details, failed_instances=failed_instances or []
            )
            # H8: one broken webhook must not silence the rest.
            try:
                self._send_one(hook, message)
            except Exception as exc:
                log.error("Webhook %s failed; continuing: %s", hook.name, exc)

    def send_test(self, session: Session, notification_id: int) -> tuple[bool, str]:
        """Send a test message to a single configured webhook."""
        hook = session.get(Notification, notification_id)
        if hook is None:
            return False, f"Notification {notification_id} not found"
        msg = self._format_message(
            hook,
            status="TEST",
            details="This is a test notification from pfsense-backup.",
            failed_instances=[],
        )
        try:
            self._send_one(hook, msg)
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

    # Discord caps webhook `content` at 2000 chars. Keep a safety margin.
    _DISCORD_CONTENT_MAX = 1997  # 2000 - "..."

    def _send_one(self, hook: Notification, message: str) -> None:
        # M2: URL is stored as-is. Don't expandvars on it — if the user
        # embeds a literal `$FOO` we must not rewrite silently. Headers,
        # on the other hand, commonly carry `Authorization: Bearer ${TOKEN}`
        # and expanding those once per call is the useful pattern.
        url = hook.url
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if hook.headers_json:
            for k, v in json.loads(hook.headers_json).items():
                headers[k] = os.path.expandvars(str(v))

        payload: dict[str, Any] | None
        is_discord = "discord.com/api/webhooks" in url.lower()
        is_healthcheck = "healthchecks" in url.lower()

        if hook.payload_template_json:
            tmpl = json.loads(hook.payload_template_json)
            payload = {
                k: (v.format(message=message) if isinstance(v, str) else v) for k, v in tmpl.items()
            }
        elif is_discord:
            payload = {"content": message}
        elif is_healthcheck:
            payload = None
        else:
            payload = {"text": message, "timestamp": datetime.now().isoformat()}

        # M3: Discord rejects payload.content > 2000 chars. Truncate any
        # `content` field when sending to a Discord webhook (whether the
        # user supplied a template or we built the default).
        if payload is not None and is_discord:
            content = payload.get("content")
            if isinstance(content, str) and len(content) > self._DISCORD_CONTENT_MAX:
                payload["content"] = content[: self._DISCORD_CONTENT_MAX] + "..."
                log.warning(
                    "Truncated Discord content for %s from %d to %d chars",
                    hook.name,
                    len(content),
                    self._DISCORD_CONTENT_MAX + 3,
                )

        try:
            if payload is None:
                # Healthchecks.io ping — GET/POST with no body.
                resp = requests.post(
                    url,
                    headers={"User-Agent": "pfSense-Backup-Manager"},
                    timeout=hook.timeout_seconds,
                )
            else:
                resp = requests.post(
                    url, json=payload, headers=headers, timeout=hook.timeout_seconds
                )
            resp.raise_for_status()
            log.info("Notification sent to %s", hook.name)
            self._metrics.record_notification(hook.name, True)
        except Exception as exc:
            log.error("Notification %s failed: %s", hook.name, exc)
            self._metrics.record_notification(hook.name, False)
            raise
