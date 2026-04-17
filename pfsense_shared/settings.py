"""Environment-backed settings for both the worker and the web service."""

from pathlib import Path

from pydantic import Field, field_validator
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
    pfsense_backup_secret_key_file: Path = Field(default=KEY_FILE)
    backups_dir: Path = Field(default=BACKUPS_DIR)
    log_level: str = Field(default="INFO")


class WorkerSettings(CommonSettings):
    metrics_port: int = Field(default=8000)
    zmq_pull_bind: str = Field(default="tcp://0.0.0.0:5555")
    zmq_pub_bind: str = Field(default="tcp://0.0.0.0:5556")
    heartbeat_seconds: float = Field(default=5.0)
    hostname: str = Field(default="pfsense-backup")


class WebSettings(CommonSettings):
    web_port: int = Field(default=8080)

    session_secret: str
    oidc_issuer: str
    oidc_client_id: str
    oidc_client_secret: str
    oidc_redirect_url: str
    oidc_allowed_emails: list[str] = Field(default_factory=list)

    worker_push_url: str = Field(default="tcp://worker:5555")
    worker_sub_url: str = Field(default="tcp://worker:5556")

    @field_validator("oidc_allowed_emails", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip().lower() for item in v.split(",") if item.strip()]
        return v

    @field_validator("oidc_allowed_emails")
    @classmethod
    def _lowercase(cls, v: list[str]) -> list[str]:
        return [e.lower() for e in v]
