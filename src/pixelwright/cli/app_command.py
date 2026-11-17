"""`pw open`: start the desktop app on a project (or on the start screen)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pixelwright.cli.registry import Outcome, Param, PwError, command
from pixelwright.project import ProjectError, find_project


@command(
    "open",
    "open the app on a project folder, or on an image inside one",
    Param("path", help="project folder or a file inside it (default: here, if it is a project)",
          positional=True),
    Param("debug", "bool", help="open the web inspector"),
    needs_workspace=False,
)  # fmt: skip
def cmd_open(root: Path, a: dict[str, Any]) -> Outcome:
    from pixelwright.app.window import launch

    target = Path(a["path"]) if a["path"] else root
    try:
        project: Path | None = find_project(target)
    except ProjectError:
        if a["path"]:
            raise PwError("no_project", f"{target} is not inside a pixelwright project") from None
        project = None  # start screen
    try:
        launch(project, debug=a["debug"])
    except RuntimeError as exc:
        raise PwError("no_app", str(exc)) from exc
    return Outcome(data={"project": str(project) if project else None}, text="App closed.")
