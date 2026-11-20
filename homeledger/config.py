"""Paths and constants."""
import os
import sys
from pathlib import Path

VERSION = "1.1.0"
APP_NAME = "HomeLedger"
DEFAULT_PORT = int(os.environ.get("HOMELEDGER_PORT", "8765"))
PORT_RANGE = 10  # tries DEFAULT_PORT .. DEFAULT_PORT + PORT_RANGE - 1


def data_dir() -> Path:
    """Where the database, backups and logs live (kept apart from the program files)."""
    env = os.environ.get("HOMELEDGER_DATA")
    if env:
        base = Path(env)
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "HomeLedger"
    else:
        base = Path.home() / ".local" / "share" / "HomeLedger"
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    return data_dir() / "homeledger.db"


def backup_dir() -> Path:
    p = data_dir() / "backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


def log_dir() -> Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def static_dir() -> Path:
    return Path(__file__).resolve().parent / "static"


def default_copy_dir() -> str:
    """Suggested second-copy folder for backups (inside Documents)."""
    return str(Path.home() / "Documents" / "HomeLedger Backups")
