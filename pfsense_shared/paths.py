"""Canonical filesystem paths inside the containers."""

from pathlib import Path

DATA_DIR = Path("/app/data")
DB_FILE = DATA_DIR / "app.db"
KEY_FILE = DATA_DIR / "secret.key"
BACKUPS_DIR = Path("/backups")


def resolve_backup_path(raw: str | Path) -> Path:
    """Absolute paths as-is; relative ones resolve under ``BACKUPS_DIR``."""
    p = Path(raw)
    return p if p.is_absolute() else BACKUPS_DIR / p
