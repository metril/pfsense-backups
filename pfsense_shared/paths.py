"""Canonical filesystem paths inside the containers."""

from pathlib import Path

DATA_DIR = Path("/app/data")
DB_FILE = DATA_DIR / "app.db"
KEY_FILE = DATA_DIR / "secret.key"
BACKUPS_DIR = Path("/backups")
