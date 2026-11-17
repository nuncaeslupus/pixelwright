"""Recently opened projects, kept in the user's config folder."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

LIMIT = 8


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "pixelwright"


def _file() -> Path:
    return config_dir() / "recent.json"


def load_recent() -> list[str]:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [p for p in data if isinstance(p, str) and Path(p).is_dir()][:LIMIT]


def remember(project_root: Path) -> list[str]:
    path = str(project_root.resolve())
    items = [path, *(p for p in load_recent() if p != path)][:LIMIT]
    _file().parent.mkdir(parents=True, exist_ok=True)
    _file().write_text(json.dumps(items, indent=1), encoding="utf-8")
    return items
