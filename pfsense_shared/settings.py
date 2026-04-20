"""Environment-backed settings for both the worker and the web service."""

from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .paths import BACKUPS_DIR, DB_FILE, KEY_FILE


class CommonSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_db_url: str = Field(default=f"sqlite:///{DB_FILE}")
    pfsense_backups_secret_key_file: Path = Field(default=KEY_FILE)
    backups_dir: Path = Field(default=BACKUPS_DIR)
    log_level: str = Field(default="INFO")


class WorkerSettings(CommonSettings):
    metrics_port: int = Field(default=8000)
    zmq_pull_bind: str = Field(default="tcp://0.0.0.0:5555")
    zmq_pub_bind: str = Field(default="tcp://0.0.0.0:5556")
    heartbeat_seconds: float = Field(default=5.0)
    # Optional operator-set identifier included in notification bodies.
    # Aliased to PFSENSE_BACKUPS_HOSTNAME so we don't pick up the container's
    # auto-populated $HOSTNAME (which is just the Docker container id) or the
    # operator's shell $HOSTNAME (which leaks the dev machine's name). Empty
    # default means the notifier omits the Host: line entirely.
    hostname: str = Field(default="", alias="PFSENSE_BACKUPS_HOSTNAME")


class WebSettings(CommonSettings):
    web_port: int = Field(default=8080)
    # H13: flip to true to drop the Secure/https_only flag so local dev over
    # plain http://localhost works without Traefik.
    dev_mode: bool = Field(default=False)

    session_secret: str
    oidc_issuer: str
    oidc_client_id: str
    oidc_client_secret: str
    oidc_redirect_url: str
    # CSV of emails. Kept as a plain str at the env boundary because
    # pydantic-settings insists on JSON-decoding list fields, which makes
    # `OIDC_ALLOWED_EMAILS=a@x,b@y` fail parsing. Access the parsed list
    # via `settings.oidc_allowed_emails`.
    oidc_allowed_emails_raw: str = Field(default="", alias="OIDC_ALLOWED_EMAILS")

    worker_push_url: str = Field(default="tcp://worker:5555")
    worker_sub_url: str = Field(default="tcp://worker:5556")

    # A3: rate limiting. slowapi accepts strings like "10/minute", "200/hour".
    rate_limit_enabled: bool = Field(default=True)
    rate_limit_default: str = Field(default="100/minute")
    rate_limit_login: str = Field(default="10/minute")
    rate_limit_ws: str = Field(default="30/minute")

    # v0.20.0 — restrict which upstream IPs may spoof ``X-Forwarded-*``
    # headers. Empty (default) means "only loopback" so a client hitting
    # the container directly can't forge ``X-Forwarded-Proto: https`` to
    # bypass the session cookie's Secure flag. Set to the reverse-proxy
    # address when deployed behind Traefik / nginx on another host.
    # Comma-separated; ``"*"`` trusts every upstream (retained as an
    # explicit opt-in rather than the historical default).
    trusted_proxies: str = Field(
        default="127.0.0.1,::1",
        alias="TRUSTED_PROXIES",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def trusted_proxies_list(self) -> list[str] | str:
        raw = self.trusted_proxies.strip()
        if raw == "*":
            return "*"
        return [h.strip() for h in raw.split(",") if h.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def oidc_allowed_emails(self) -> list[str]:
        return [
            e.strip().lower()
            for e in self.oidc_allowed_emails_raw.split(",")
            if e.strip()
        ]
