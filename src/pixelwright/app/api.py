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
from pixelwright.issues import IssueError, IssueLog
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
        self._pick_files: Callable[[], list[str]] | None = None
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

    # --- Project screen --------------------------------------------------------------

    def bind_file_picker(self, picker: Callable[[], list[str]]) -> None:
        self._pick_files = picker

    @_safe
    def add_images(self, paths: list[str], category: str) -> Result:
        """Each image becomes its own asset in `category`; the scripts run right away."""
        project = self.project
        category = category.strip().strip("/")
        if not category or not all(flow.asset_name(p) == p for p in category.split("/")):
            raise ProjectError(f"category must be lowercase words joined by '-': {category!r}")
        made = [flow.ingest(project, Path(p), category).rel for p in paths]
        return {"added": made}

    @_safe
    def pick_and_add(self, category: str) -> Result:
        picker = self._pick_files
        if picker is None:
            raise ProjectError("file picker not available")
        paths = picker()
        if not paths:
            return {"cancelled": True}
        res = self.add_images(paths, category)
        if not res["ok"]:
            raise ProjectError(res["error"])
        return {"added": res["added"]}

    @_safe
    def scan(self) -> Result:
        """Images saved into a category folder outside the app become assets."""
        return {"added": [a.rel for a in flow.scan(self.project)]}

    @_safe
    def review_all_new(self) -> Result:
        """Ask the AI to review every asset in review that it has not looked at yet."""
        asked = []
        for asset in list_assets(self.project):
            if asset.meta().state != "review" or asset.latest() is None:
                continue
            issues = IssueLog(asset).state().issues.values()
            if any(i.author == "ai" or i.target == "ai" for i in issues):
                continue
            IssueLog(asset).raise_issue(
                "Review this asset", author="person", kind="request", target="ai"
            )
            asked.append(asset.rel)
        return {"asked": asked}
