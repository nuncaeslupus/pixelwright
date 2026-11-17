"""What the page can call (pywebview `js_api`): plain methods, JSON in and out.

Every method returns `{"ok": true, ...}` or `{"ok": false, "error": "..."}` so the page
can show errors inline next to the action, never as a transient toast.
"""

from __future__ import annotations

import base64
import shutil
import subprocess
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

from PIL import Image as PILImage

from pixelwright import flow
from pixelwright.app import recent
from pixelwright.asset import Asset, AssetError, list_assets, open_asset
from pixelwright.issues import IssueError, IssueLog
from pixelwright.project import Project, ProjectError, find_project, load_project

Result = dict[str, Any]
EDIT_FILE = "work/edit.png"


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
        added = [a.rel for a in flow.scan(self.project)]
        edited = []
        for asset in list_assets(self.project):
            edit = asset.path / EDIT_FILE
            latest = asset.latest()
            if not edit.is_file() or latest is None:
                continue
            if edit.read_bytes() != asset.version_path(latest).read_bytes():
                with PILImage.open(edit) as im:
                    im.load()
                    asset.add_version(im)
                shutil.copyfile(asset.version_path(asset.latest() or latest), edit)
                edited.append(asset.rel)
        return {"added": added, "edited": edited}

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

    # --- Asset screen ----------------------------------------------------------------

    def _asset(self, rel: str) -> Asset:
        return open_asset(self.project, self.project.assets_dir / rel)

    @_safe
    def asset_detail(self, rel: str) -> Result:
        """Everything the Asset screen shows: versions, issues with their fixes, next step."""
        asset = self._asset(rel)
        meta = asset.meta()
        st = IssueLog(asset).state()
        versions = [
            {
                "name": v,
                "image": _data_uri(asset.version_path(v)),
                "starred": v in meta.starred,
                "final": v == meta.final,
            }
            for v in asset.versions()
        ]
        issues = []
        for issue in st.issues.values():
            fixes = [
                {
                    "id": st.fixes[f].id,
                    "by": st.fixes[f].by,
                    "state": st.fixes[f].state,
                    "base": st.fixes[f].base,
                    "image": _data_uri(asset.path / st.fixes[f].image),
                }
                for f in issue.fixes
            ]
            issues.append({**issue.__dict__, "fixes": fixes})
        canvas = asset.settings().canvas
        return {
            "asset": asset.rel,
            "brief": meta.brief,
            "state": meta.state,
            "final": meta.final,
            "latest": asset.latest(),
            "canvas": canvas,
            "versions": versions,
            "issues": issues,
            "next": flow.next_step(asset).to_dict(),
            "can_undo": any(not g["undone"] for g in st.groups),
            "can_redo": bool(st.groups and st.groups[-1]["undone"]),
        }

    @_safe
    def ask_ai(self, rel: str, message: str, areas: list[list[int]] | None = None) -> Result:
        if not message.strip():
            raise IssueError("say what the AI should look at")
        issue = IssueLog(self._asset(rel)).raise_issue(
            message.strip(),
            author="person",
            kind="request",
            target="ai",
            areas=[{"box": [int(v) for v in box]} for box in areas or []],
        )
        return {"issue": issue.id}

    @_safe
    def raise_note(self, rel: str, message: str, areas: list[list[int]] | None = None) -> Result:
        """An issue the person raises for themself (to fix outside, e.g. in Aseprite)."""
        if not message.strip():
            raise IssueError("describe the issue")
        issue = IssueLog(self._asset(rel)).raise_issue(
            message.strip(),
            author="person",
            kind="note",
            areas=[{"box": [int(v) for v in box]} for box in areas or []],
        )
        return {"issue": issue.id}

    @_safe
    def accept(self, rel: str, fix_ids: list[str]) -> Result:
        return {"version": IssueLog(self._asset(rel)).accept(fix_ids)}

    @_safe
    def reject_fix(self, rel: str, fix_id: str, reason: str) -> Result:
        IssueLog(self._asset(rel)).reject_fix(fix_id, reason)
        return {}

    @_safe
    def reject_issue(
        self, rel: str, issue_id: str, reason: str, promote: bool = False, scope: str = "asset"
    ) -> Result:
        IssueLog(self._asset(rel)).reject_issue(issue_id, reason, promote=promote, scope=scope)
        return {}

    @_safe
    def reply(self, rel: str, issue_id: str, message: str) -> Result:
        if not message.strip():
            raise IssueError("write a reply")
        IssueLog(self._asset(rel)).reply(issue_id, message.strip(), by="person")
        return {}

    @_safe
    def mark_fixed(self, rel: str, issue_id: str) -> Result:
        IssueLog(self._asset(rel)).mark_fixed(issue_id)
        return {}

    @_safe
    def undo(self, rel: str) -> Result:
        return {"version": IssueLog(self._asset(rel)).undo()}

    @_safe
    def redo(self, rel: str) -> Result:
        return {"version": IssueLog(self._asset(rel)).redo()}

    @_safe
    def star(self, rel: str, version: str, on: bool = True) -> Result:
        self._asset(rel).star(version, on)
        return {}

    @_safe
    def finish(self, rel: str, version: str | None = None) -> Result:
        return {"export": str(self._asset(rel).finish(version))}

    @_safe
    def open_in_aseprite(self, rel: str) -> Result:
        """Copy the current version to `work/edit.png` and open it; saving there adds a
        new version (picked up by `scan`)."""
        asset = self._asset(rel)
        latest = asset.latest()
        if latest is None:
            raise AssetError(f"{rel}: no version to edit")
        exe = shutil.which("aseprite")
        if exe is None:
            raise AssetError("Aseprite was not found on this computer (no `aseprite` on PATH)")
        edit = asset.path / EDIT_FILE
        edit.parent.mkdir(exist_ok=True)
        shutil.copyfile(asset.version_path(latest), edit)
        subprocess.Popen([exe, str(edit)], start_new_session=True)
        return {"file": str(edit)}
