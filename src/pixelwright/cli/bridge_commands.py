"""`pw wait` and `pw requests`: how an AI session picks up requests from the app."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pixelwright.bridge import hook_message, pending_requests, wait_for_requests
from pixelwright.cli.registry import Outcome, Param, PwError, command
from pixelwright.project import Project, ProjectError, load_project


def _project(root: Path) -> Project:
    try:
        return load_project(root)
    except ProjectError as exc:
        raise PwError("no_project", str(exc)) from exc


def _text(pending: list[dict[str, Any]]) -> str:
    if not pending:
        return "No requests are waiting."
    return "\n".join(f"{p['asset']}  {p['issue']}  {p['message']}" for p in pending)


@command(
    "wait",
    "block until the app leaves a request for the AI, then print every pending one",
    Param("timeout", kind="float", help="give up after this many seconds (default: never)"),
    Param("poll", kind="float", help="seconds between checks", default=0.5),
)
def cmd_wait(root: Path, a: dict[str, Any]) -> Outcome:
    pending = wait_for_requests(_project(root), timeout=a["timeout"], poll=a["poll"])
    return Outcome(data={"requests": pending}, text=_text(pending))


@command(
    "requests",
    "list the requests from the app that wait on the AI",
    Param("hook", kind="bool", help="print one line for a session-start hook (empty if none)"),
)
def cmd_requests(root: Path, a: dict[str, Any]) -> Outcome:
    project = _project(root)
    if a["hook"]:
        message = hook_message(project)
        return Outcome(data={"message": message}, text=message)
    pending = pending_requests(project)
    return Outcome(data={"requests": pending}, text=_text(pending))
