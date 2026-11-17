"""The AI bridge: requests raised in the app wait in each asset's `issues.jsonl`.

An AI session listens with `pw wait` (blocks until something is pending, costs nothing
while idle) or checks on demand with `pw requests`; a session-start hook can call
`pw requests --hook` to say how many are waiting.
"""

from __future__ import annotations

import time
from typing import Any

from pixelwright.asset import list_assets
from pixelwright.issues import ISSUES_FILE, IssueLog
from pixelwright.project import Project


def pending_requests(project: Project) -> list[dict[str, Any]]:
    """Every open issue that waits on the AI, oldest asset path first."""
    found: list[dict[str, Any]] = []
    for asset in list_assets(project):
        for issue in IssueLog(asset).pending_for_ai():
            found.append(
                {
                    "asset": asset.rel,
                    "issue": issue.id,
                    "version": issue.version,
                    "message": issue.message,
                    "areas": issue.areas,
                    "replies": issue.replies,
                    "fixes": issue.fixes,
                }
            )
    return found


def _signature(project: Project) -> tuple[tuple[str, int, int], ...]:
    files = sorted(project.assets_dir.rglob(ISSUES_FILE)) if project.assets_dir.is_dir() else []
    sig = []
    for f in files:
        try:
            st = f.stat()
        except FileNotFoundError:
            continue
        sig.append((str(f), st.st_mtime_ns, st.st_size))
    return tuple(sig)


def wait_for_requests(
    project: Project, timeout: float | None = None, poll: float = 0.5
) -> list[dict[str, Any]]:
    """Block until at least one request is pending; return them all ([] on timeout).

    Logs are re-read only when one changes, so an idle wait is a cheap stat loop.
    """
    deadline = None if timeout is None else time.monotonic() + timeout
    last: tuple[tuple[str, int, int], ...] | None = None
    while True:
        sig = _signature(project)
        if sig != last:
            last = sig
            pending = pending_requests(project)
            if pending:
                return pending
        if deadline is not None and time.monotonic() >= deadline:
            return []
        time.sleep(poll)


def hook_message(project: Project) -> str:
    n = len(pending_requests(project))
    if n == 0:
        return ""
    noun = "request" if n == 1 else "requests"
    return f"pixelwright: {n} {noun} from the app wait for you. Run `pw requests` to see them."
