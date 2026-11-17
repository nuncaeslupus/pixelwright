"""What the page can call (pywebview `js_api`): plain methods, JSON in and out.

Every method returns `{"ok": true, ...}` or `{"ok": false, "error": "..."}` so the page
can show errors inline next to the action, never as a transient toast.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

from pixelwright import flow
from pixelwright.app import recent
from pixelwright.asset import AssetError, list_assets
from pixelwright.issues import IssueError
from pixelwright.project import Project, ProjectError, find_project, load_project

Result = dict[str, Any]


def _safe(fn: Callable[..., Result]) -> Callable[..., Result]:
    @wraps(fn)
    def wrapped(*args: Any, **kwargs: Any) -> Result:
        try:
            return {"ok": True, **fn(*args, **kwargs)}
        except (AssetError, IssueError, ProjectError, OSError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}

    return wrapped


def _data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


class AppApi:
    def __init__(self, project: Path | None = None) -> None:
        self._project: Project | None = None
        self._pick_folder: Callable[[], str | None] | None = None
        if project is not None:
            self.open_project(str(project))

    def bind_folder_picker(self, picker: Callable[[], str | None]) -> None:
        self._pick_folder = picker

    @property
    def project(self) -> Project:
        if self._project is None:
            raise ProjectError("no project is open")
        return self._project

    @_safe
    def recent_projects(self) -> Result:
        return {"projects": [{"path": p, "name": Path(p).name} for p in recent.load_recent()]}

    @_safe
    def open_project(self, path: str) -> Result:
        """Open a project folder, or the project around a file or folder inside one."""
        root = find_project(Path(path).expanduser())
        self._project = load_project(root)
        recent.remember(root)
        return {"project": {"name": self._project.name, "path": str(root)}}

    @_safe
    def pick_and_open(self) -> Result:
        if self._pick_folder is None:
            raise ProjectError("folder picker not available")
        chosen = self._pick_folder()
        if not chosen:
            return {"cancelled": True}
        result = self.open_project(chosen)
        if not result["ok"]:
            raise ProjectError(result["error"])
        return {"project": result["project"]}

    @_safe
    def list_assets(self) -> Result:
        """Every asset with its state, next step and a thumbnail of its latest version."""
        project = self.project
        assets = list_assets(project)
        rows = flow.status(assets)
        for row, asset in zip(rows, assets, strict=True):
            row["category"] = asset.category
            row["thumb"] = _data_uri(asset.version_path(row["latest"])) if row["latest"] else None
        return {
            "project": {"name": project.name, "path": str(project.root)},
            "categories": project.categories(),
            "assets": rows,
        }
