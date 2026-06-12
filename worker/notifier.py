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
import re
from datetime import datetime
from typing import Any

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from pfsense_shared.backup_diff_storage import ChangeSummary
from pfsense_shared.models import Instance, Notification

from .prometheus_metrics import PrometheusMetrics

log = logging.getLogger(__name__)


# Per-outcome styling threaded into every channel so plain-text
# channels get an emoji prefix and rich channels (Discord embeds,
# Ntfy tags) get native decoration.
#   (emoji, hex_color, ntfy_tag, label)
_STYLE_SUCCESS = ("\N{WHITE HEAVY CHECK MARK}", 0x22C55E, "white_check_mark", "Backup succeeded")
_STYLE_FAILURE = ("\N{CROSS MARK}", 0xEF4444, "x", "Backup failed")
_STYLE_TEST = ("\N{BELL}", 0x3B82F6, "bell", "Test notification")
_STYLE_START = ("\N{ROCKET}", 0x3B82F6, "rocket", "Backup run started")


def _style(is_success: bool, is_test: bool) -> tuple[str, int, str, str]:
    if is_test:
        return _STYLE_TEST
    return _STYLE_SUCCESS if is_success else _STYLE_FAILURE


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
        change_summary: ChangeSummary | None = None,
    ) -> None:
        """Fire one terminal notification per enabled row.

        Per-instance scope filters (``instance_ids_json``) are evaluated
        per row: scoped rows only fire when one of the scoped instances
        actually ran, and the message / Healthchecks ping path reflect
        the scoped subset rather than the aggregate run outcome.

        ``change_summary`` (single-instance runs only) gates rows with
        ``trigger="change"`` and appends a "Changes: …" line to every
        message that fires while it's present.
        """
        failed_instances = failed_instances or []
        succeeded_instances = succeeded_instances or []
        has_changes = change_summary is not None and not change_summary.is_empty

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
            effective_success, scoped_failed, scoped_ok, scoped_details = scope
            if not self._should_send(
                hook.trigger, effective_success, has_changes=has_changes
            ):
                continue
            is_change_row = hook.trigger.lower() == "change"
            status_label = (
                "CHANGED"
                if is_change_row
                else ("SUCCESS" if effective_success else "FAILURE")
            )
            message = self._format_message(
                hook,
                status=status_label,
                details=scoped_details,
                failed_instances=scoped_failed,
                succeeded_instances=scoped_ok,
            )
            if has_changes and change_summary is not None:
                message += f"\n{change_summary.as_line()}"
            # H8: one broken webhook must not silence the rest.
            try:
                self._dispatch(
                    hook,
                    message,
                    is_success=effective_success,
                    failed_instances=scoped_failed,
                    succeeded_instances=scoped_ok,
                    changes=(
                        change_summary.as_dict()
                        if has_changes and change_summary is not None
                        else None
                    ),
                )
            except Exception as exc:
                log.error("Webhook %s failed; continuing: %s", hook.name, exc)

    def send_change_only(
        self,
        session: Session,
        *,
        instance_name: str,
        change_summary: ChangeSummary,
    ) -> None:
        """Per-instance fan-out used by ``backup_all`` sweeps: outcome
        rows get one aggregate ``send`` at the end of the sweep, but
        ``change`` rows are inherently per-instance, so the manager
        calls this after each instance whose vs-previous diff was
        non-empty."""
        if change_summary.is_empty:
            return
        rows = (
            session.execute(
                select(Notification).where(
                    Notification.enabled.is_(True),
                    Notification.trigger == "change",
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return
        name_to_id = self._name_to_id_map(session)
        instance_id = name_to_id.get(instance_name)
        for hook in rows:
            if hook.instance_ids_json:
                try:
                    scoped = set(json.loads(hook.instance_ids_json))
                except (TypeError, ValueError):
                    continue
                if instance_id not in scoped:
                    continue
            message = self._format_message(
                hook,
                status="CHANGED",
                details=f"Config changed for {instance_name}",
                failed_instances=[],
                succeeded_instances=[instance_name],
            )
            message += f"\n{change_summary.as_line()}"
            try:
                self._dispatch(
                    hook,
                    message,
                    is_success=True,
                    failed_instances=[],
                    succeeded_instances=[instance_name],
                    changes=change_summary.as_dict(),
                )
            except Exception as exc:
                log.error("Webhook %s failed; continuing: %s", hook.name, exc)

    def send_stale(
        self,
        session: Session,
        *,
        instance_id: int,
        instance_name: str,
        detail: str,
        is_recovery: bool,
    ) -> None:
        """Staleness alert / recovery for one instance. Routes to rows
        with trigger ``stale`` or ``always`` — never ``failure``
        (operators configured those for "a run failed", not "the cron
        went quiet"). kind=healthchecks rows are excluded: Healthchecks
        is itself a missed-ping staleness detector, and a ``/fail``
        ping here would mark the *backup* check red over a scheduling
        gap it is already tracking."""
        rows = (
            session.execute(
                select(Notification).where(
                    Notification.enabled.is_(True),
                    Notification.trigger.in_(["stale", "always"]),
                    Notification.kind != "healthchecks",
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return
        status = "RECOVERED" if is_recovery else "STALE"
        for hook in rows:
            if hook.instance_ids_json:
                try:
                    scoped = set(json.loads(hook.instance_ids_json))
                except (TypeError, ValueError):
                    continue
                if instance_id not in scoped:
                    continue
            message = self._format_message(
                hook,
                status=status,
                details=detail,
                failed_instances=[] if is_recovery else [instance_name],
                succeeded_instances=[instance_name] if is_recovery else [],
            )
            try:
                self._dispatch(
                    hook,
                    message,
                    is_success=is_recovery,
                    failed_instances=[] if is_recovery else [instance_name],
                    succeeded_instances=[instance_name] if is_recovery else [],
                )
            except Exception as exc:
                log.error("Webhook %s failed; continuing: %s", hook.name, exc)

    def ping_starts(
        self, session: Session, *, instance_id: int | None = None
    ) -> None:
        """Fire ``/start`` pings for all enabled Healthchecks rows.

        Called at the top of a backup run so Healthchecks can compute
        run duration between ``/start`` and the terminal ping.

        When ``instance_id`` is None (aggregate sweep), a scoped row
        only pings if at least one of its scoped instances is
        currently enabled — mirrors the aggregate notify semantics.

        When ``instance_id`` is given (single-instance run), a scoped
        row only pings if its scope contains that instance. Unscoped
        rows always ping in either mode.
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
        if instance_id is None:
            enabled_ids = {
                iid
                for (iid,) in session.execute(
                    select(Instance.id).where(Instance.enabled.is_(True))
                ).all()
            }
        lines = [f"{_STYLE_START[0]} Backup run started"]
        if self._hostname:
            lines.append(f"Host: {self._hostname}")
        lines.append(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        message = "\n".join(lines)
        for hook in rows:
            if hook.instance_ids_json:
                try:
                    scoped = set(json.loads(hook.instance_ids_json))
                except (TypeError, ValueError):
                    continue
                if instance_id is None:
                    if not (scoped & enabled_ids):
                        continue
                elif instance_id not in scoped:
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
            succeeded_instances=[],
        )
        try:
            # Test sends as a "success" for Healthchecks so the check
            # turns green rather than red; a red test would look like
            # a real failure on the user's dashboard.
            self._dispatch(
                hook, msg, is_success=True, is_test=True,
                failed_instances=[], succeeded_instances=[],
            )
            return True, "sent"
        except Exception as exc:
            return False, str(exc)

    # -------------------------------------------------------------- #
    # internals
    # -------------------------------------------------------------- #

    @staticmethod
    def _should_send(
        trigger: str, is_success: bool, *, has_changes: bool = False
    ) -> bool:
        t = trigger.lower()
        if t == "always":
            return True
        if t == "change":
            # Only fires for a successful run whose vs-previous diff is
            # non-empty. First-ever backups have no previous → no fire.
            return is_success and has_changes
        if t == "stale":
            # Staleness rows are driven by Notifier.send_stale, never by
            # terminal backup outcomes.
            return False
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
    ) -> tuple[bool, list[str], list[str], str] | None:
        """Compute (effective_success, scoped_failed, scoped_ok, details).

        Returns None when the row is scoped but none of its scoped
        instances ran this cycle (the row should be skipped).
        """
        if not hook.instance_ids_json:
            return (
                aggregate_is_success,
                failed_instances,
                succeeded_instances,
                aggregate_details,
            )
        try:
            allowed_ids = set(json.loads(hook.instance_ids_json))
        except (TypeError, ValueError):
            return None
        if not allowed_ids:
            return (
                aggregate_is_success,
                failed_instances,
                succeeded_instances,
                aggregate_details,
            )
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
        return scoped_success, failed_in_scope, ok_in_scope, details

    def _format_message(
        self,
        hook: Notification,
        *,
        status: str,
        details: str,
        failed_instances: list[str],
        succeeded_instances: list[str],
    ) -> str:
        msg = hook.message_format.format(status=status, details=details)
        if hook.include_instance_details:
            if succeeded_instances:
                msg += f"\nSucceeded: {', '.join(succeeded_instances)}"
            if failed_instances:
                msg += f"\nFailed: {', '.join(failed_instances)}"
        msg += f"\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        if self._hostname:
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

    def _dispatch(
        self,
        hook: Notification,
        message: str,
        *,
        is_success: bool,
        is_test: bool = False,
        failed_instances: list[str] | None = None,
        succeeded_instances: list[str] | None = None,
        changes: dict[str, Any] | None = None,
    ) -> None:
        kind = hook.kind or "webhook"
        fi = failed_instances or []
        si = succeeded_instances or []
        # ``changes`` rides the message text for every sender; only the
        # structured-JSON senders (generic webhook, HA webhook) also get
        # it as a machine-readable key.
        if kind == "discord":
            self._send_discord(
                hook, message, is_success=is_success, is_test=is_test,
                failed_instances=fi, succeeded_instances=si,
            )
        elif kind == "home_assistant":
            self._send_home_assistant(
                hook, message, is_success=is_success, is_test=is_test,
                failed_instances=fi, succeeded_instances=si,
                changes=changes,
            )
        elif kind == "ntfy":
            self._send_ntfy(
                hook, message, is_success=is_success, is_test=is_test,
            )
        elif kind == "healthchecks":
            self._send_healthchecks(hook, message, is_success=is_success)
        else:
            self._send_webhook(
                hook, message, is_success=is_success, is_test=is_test,
                failed_instances=fi, succeeded_instances=si,
                changes=changes,
            )

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

    def _send_discord(
        self,
        hook: Notification,
        message: str,
        *,
        is_success: bool,
        is_test: bool,
        failed_instances: list[str],
        succeeded_instances: list[str],
    ) -> None:
        emoji, color, _tag, label = _style(is_success, is_test)
        # Discord embed limits: title 256, description 4096, field value 1024.
        description = message
        if len(description) > 4000:
            description = description[:3997] + "..."
        embed: dict[str, Any] = {
            "title": f"{emoji} {label}",
            "description": description,
            "color": color,
            "timestamp": datetime.now().astimezone().isoformat(),
            "footer": {"text": f"pfsense-backups · {hook.name}"},
        }
        fields: list[dict[str, Any]] = []
        if hook.include_instance_details:
            if succeeded_instances:
                value = ", ".join(succeeded_instances)
                if len(value) > 1000:
                    value = value[:997] + "..."
                ok_emoji = _STYLE_SUCCESS[0]
                fields.append(
                    {
                        "name": f"{ok_emoji} Succeeded ({len(succeeded_instances)})",
                        "value": value,
                        "inline": False,
                    }
                )
            if failed_instances:
                value = ", ".join(failed_instances)
                if len(value) > 1000:
                    value = value[:997] + "..."
                fields.append(
                    {
                        "name": f"\N{CROSS MARK} Failed ({len(failed_instances)})",
                        "value": value,
                        "inline": False,
                    }
                )
        if self._hostname:
            fields.append({"name": "Host", "value": self._hostname, "inline": True})
        if fields:
            embed["fields"] = fields
        self._post(
            hook,
            hook.url,
            json_body={"embeds": [embed]},
            headers={"Content-Type": "application/json"},
        )

    def _send_home_assistant(
        self,
        hook: Notification,
        message: str,
        *,
        is_success: bool,
        is_test: bool,
        failed_instances: list[str],
        succeeded_instances: list[str],
        changes: dict[str, Any] | None = None,
    ) -> None:
        emoji, color, _tag, label = _style(is_success, is_test)
        cfg = self._config(hook)
        token = str(cfg.get("access_token") or "")
        mode = str(cfg.get("mode") or "notify")
        base_title = str(cfg.get("title") or "pfSense Backup")
        title = f"{emoji} {base_title}"
        body_msg = f"{emoji} {message}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if mode == "webhook":
            # HA webhook triggers can read any JSON; hand automations
            # a rich payload so they can branch on status/color without
            # string-parsing the message.
            body: dict[str, Any] = {
                "message": body_msg,
                "title": title,
                "status": "success" if is_success else "failure",
                "is_test": is_test,
                "label": label,
                "emoji": emoji,
                "color": f"#{color:06x}",
            }
            if hook.include_instance_details:
                body["succeeded"] = succeeded_instances
                body["failed"] = failed_instances
            if changes is not None:
                body["changes"] = changes
            if self._hostname:
                body["host"] = self._hostname
        else:
            # notify.<service>: some integrations (HA mobile app) read
            # `data.color` / `data.notification_icon` for push styling.
            # Other integrations just ignore unknown keys.
            body = {
                "message": body_msg,
                "title": title,
                "data": {
                    "color": f"#{color:06x}",
                    "notification_icon": "mdi:server-network",
                    "tag": "pfsense-backups",
                },
            }
        self._post(hook, hook.url, json_body=body, headers=headers)

    def _send_ntfy(
        self,
        hook: Notification,
        message: str,
        *,
        is_success: bool,
        is_test: bool,
    ) -> None:
        emoji, _color, default_tag, label = _style(is_success, is_test)
        cfg = self._config(hook)
        headers: dict[str, str] = {"Title": f"{emoji} {label}"}
        priority = cfg.get("priority")
        if priority:
            headers["Priority"] = str(priority)
        elif not is_success and not is_test:
            # Bump failure pings above the default so the user's phone
            # actually wakes up; success pings stay silent by default.
            headers["Priority"] = "4"
        # User-configured tags take precedence; fall back to the
        # outcome-specific default emoji tag so the ntfy UI shows an
        # icon even without any manual config.
        tags = cfg.get("tags")
        if isinstance(tags, list) and tags:
            headers["Tags"] = ",".join(str(t) for t in tags)
        else:
            headers["Tags"] = default_tag
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
            emoji = _STYLE_START[0]
        elif is_success:
            url = base
            emoji = _STYLE_SUCCESS[0]
        else:
            url = f"{base}/fail"
            emoji = _STYLE_FAILURE[0]
        # Prefix the emoji so the Healthchecks dashboard log line is
        # visually distinguishable at a glance. Keep POST within the
        # ~10KB Healthchecks soft limit.
        body_str = (
            message
            if message.startswith(emoji)
            else f"{emoji} {message}"
        )
        body = body_str.encode("utf-8")[:8192]
        self._post(
            hook,
            url,
            data=body,
            headers={"User-Agent": "pfSense-Backup-Manager"},
        )

    def _send_webhook(
        self,
        hook: Notification,
        message: str,
        *,
        is_success: bool = True,
        is_test: bool = False,
        failed_instances: list[str] | None = None,
        succeeded_instances: list[str] | None = None,
        changes: dict[str, Any] | None = None,
    ) -> None:
        emoji, color, _tag, label = _style(is_success, is_test)
        url = hook.url
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if hook.headers_json:
            # M2: URL is stored as-is; don't expandvars. Headers commonly
            # carry `Authorization: Bearer ${TOKEN}` and benefit from
            # per-call env expansion. Expansion is intentionally
            # unrestricted, but every expansion is WARN-logged (names
            # only, never values) so a template exfiltrating worker env
            # vars to a webhook URL is visible in the logs.
            for k, v in json.loads(hook.headers_json).items():
                raw = str(v)
                headers[k] = os.path.expandvars(raw)
                if headers[k] != raw:
                    expanded = re.findall(r"\$(?:\{(\w+)\}|(\w+))", raw)
                    names = sorted({a or b for a, b in expanded})
                    log.warning(
                        "notification %r: expanded env var(s) %s into header %r",
                        hook.name, ", ".join(names) or "<unknown>", k,
                    )

        payload: dict[str, Any] | None
        is_discord_url = "discord.com/api/webhooks" in url.lower()
        decorated = f"{emoji} {message}"

        if hook.payload_template_json:
            # User-authored templates get the message verbatim so their
            # downstream schema isn't surprised by leading emoji.
            tmpl = json.loads(hook.payload_template_json)
            payload = {
                k: (v.format(message=message) if isinstance(v, str) else v)
                for k, v in tmpl.items()
            }
        elif is_discord_url:
            payload = {"content": decorated}
        else:
            # Default generic-webhook payload gains status/emoji/color
            # and (opt-in via include_instance_details) succeeded/failed
            # keys so receivers can render a rich message without
            # string-parsing.
            payload = {
                "text": decorated,
                "status": "success" if is_success else "failure",
                "label": label,
                "emoji": emoji,
                "color": f"#{color:06x}",
                "is_test": is_test,
                "timestamp": datetime.now().isoformat(),
            }
            if hook.include_instance_details:
                payload["succeeded"] = succeeded_instances or []
                payload["failed"] = failed_instances or []
            if changes is not None:
                payload["changes"] = changes

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
