"""Cross-platform app data directory and persisted settings."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

APP_DIR_NAME = "WL20Attendance"
APP_DIR_NAME_POSIX = "wl20-attendance"

DEFAULTS: Dict[str, Any] = {
    "host": "192.168.88.245",
    "port": 4370,
    "password": 0,
    "timeout": 10,
    "pause_device": False,
    "retry": True,
    "restart_if_stuck": False,
    "range_preset": "Last 30 days",
    "export_dir": "",
    "last_export_dir": "",
}


def app_data_dir() -> Path:
    """Per-OS settings directory (Windows: %APPDATA%, macOS: Application Support)."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_DIR_NAME_POSIX


def config_path() -> Path:
    return app_data_dir() / "config.json"


def load() -> Dict[str, Any]:
    settings = dict(DEFAULTS)
    path = config_path()
    try:
        if path.is_file():
            stored = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                settings.update({key: value for key, value in stored.items()
                                 if key in DEFAULTS})
    except (OSError, ValueError):
        pass
    return settings


def save(settings: Dict[str, Any]) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: settings.get(key, DEFAULTS[key]) for key in DEFAULTS}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
