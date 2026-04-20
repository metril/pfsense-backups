"""Parses ``<notifications>`` — system notification channels.

pfSense ships with four channel types under this section: SMTP email,
Growl (legacy), and Pushover. Modern builds add Slack / Teams / Telegram
via separate sub-tags or via the Notifications package. We parse what's
natively configured in config.xml.

All bearer tokens, SMTP auth passwords, Pushover user keys + app
tokens, and Telegram bot tokens go through the redaction engine.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from pfsense_shared.pfsense_redact import redact

from ._helpers import bool_flag, text


class SmtpNotifier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    ipaddress: str | None = None
    port: str | None = None
    timeout: str | None = None
    ssl: bool = False
    sslvalidate: bool = False
    fromaddress: str | None = None
    notifyemailaddress: str | None = None
    authentication_mechanism: str | None = None
    username: str | None = None
    # Redacted
    password: str | None = None


class PushoverNotifier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    # Both redacted — Pushover's API treats the user key as a long-lived
    # secret and the app api_key as the application secret.
    api_key: str | None = None
    user_key: str | None = None


class GrowlNotifier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    name: str | None = None
    notification_name: str | None = None
    ipaddress: str | None = None
    # Redacted — Growl password is a shared secret.
    password: str | None = None


class TelegramNotifier(BaseModel):
    """Some pfSense builds sprout a <telegram> sibling; best-effort parse."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    chat_id: str | None = None
    api_token: str | None = None  # redacted


class SlackNotifier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    webhook_url: str | None = None  # redacted — token is in the URL


class NotificationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    smtp: SmtpNotifier | None = None
    pushover: PushoverNotifier | None = None
    growl: GrowlNotifier | None = None
    telegram: TelegramNotifier | None = None
    slack: SlackNotifier | None = None


def _parse_smtp(el: Element | None) -> SmtpNotifier | None:
    if el is None:
        return None
    # pfSense stores "enabled" either as a flag child or via the
    # deprecated <disable>yes</disable> inverse.
    disabled = (text(el, "disable") or "").lower() in ("yes", "true", "on", "1")
    return SmtpNotifier(
        enabled=not disabled if el.find("disable") is not None else bool_flag(el, "enable"),
        ipaddress=text(el, "ipaddress"),
        port=text(el, "port"),
        timeout=text(el, "timeout"),
        ssl=bool_flag(el, "ssl"),
        sslvalidate=bool_flag(el, "sslvalidate"),
        fromaddress=text(el, "fromaddress"),
        notifyemailaddress=text(el, "notifyemailaddress"),
        authentication_mechanism=text(el, "authentication_mechanism"),
        username=text(el, "username"),
        password=redact("password", text(el, "password")),
    )


def _parse_pushover(el: Element | None) -> PushoverNotifier | None:
    if el is None:
        return None
    disabled = (text(el, "disable") or "").lower() in ("yes", "true", "on", "1")
    return PushoverNotifier(
        enabled=not disabled if el.find("disable") is not None else bool_flag(el, "enable"),
        api_key=redact("api_key", text(el, "api_key") or text(el, "apikey")),
        user_key=redact("user_key", text(el, "user_key") or text(el, "userkey")),
    )


def _parse_growl(el: Element | None) -> GrowlNotifier | None:
    if el is None:
        return None
    disabled = (text(el, "disable") or "").lower() in ("yes", "true", "on", "1")
    return GrowlNotifier(
        enabled=not disabled if el.find("disable") is not None else bool_flag(el, "enable"),
        name=text(el, "name"),
        notification_name=text(el, "notification_name"),
        ipaddress=text(el, "ipaddress"),
        password=redact("password", text(el, "password")),
    )


def _parse_telegram(el: Element | None) -> TelegramNotifier | None:
    if el is None:
        return None
    return TelegramNotifier(
        enabled=bool_flag(el, "enable"),
        chat_id=text(el, "chat_id") or text(el, "chatid"),
        api_token=redact("api_token", text(el, "api_token") or text(el, "apitoken")),
    )


def _parse_slack(el: Element | None) -> SlackNotifier | None:
    if el is None:
        return None
    return SlackNotifier(
        enabled=bool_flag(el, "enable"),
        webhook_url=redact("webhook_url", text(el, "webhook_url") or text(el, "webhookurl")),
    )


def parse(root: Element) -> NotificationConfig | None:
    el = root.find("notifications")
    if el is None:
        return None
    smtp = _parse_smtp(el.find("smtp"))
    pushover = _parse_pushover(el.find("pushover"))
    growl = _parse_growl(el.find("growl"))
    telegram = _parse_telegram(el.find("telegram"))
    slack = _parse_slack(el.find("slack"))
    if all(x is None for x in (smtp, pushover, growl, telegram, slack)):
        return None
    return NotificationConfig(
        smtp=smtp,
        pushover=pushover,
        growl=growl,
        telegram=telegram,
        slack=slack,
    )
