"""The `view` command: start (or reuse) the viewer for a workspace."""

from __future__ import annotations

import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

from pixelwright.cli.registry import Outcome, Param, PwError, command
from pixelwright.viewer.server import Viewer
from pixelwright.workspace import Workspace

RUNNING: dict[Path, Viewer] = {}
DEFAULT_PORT = 7313


def start(root: Path, port: int = DEFAULT_PORT) -> Viewer:
    """The viewer already serving `root`, or a new one (any free port if `port` is taken)."""
    if root in RUNNING:
        return RUNNING[root]
    try:
        viewer = Viewer(root, port)
    except OSError:
        if port == 0:
            raise
        viewer = Viewer(root, 0)
    RUNNING[root] = viewer.start()
    return viewer


def stop(root: Path) -> None:
    viewer = RUNNING.pop(root, None)
    if viewer is not None:
        viewer.shutdown()
        viewer.server_close()


@command(
    "view",
    "open the local viewer (asset list, or one asset with --open id[/version])",
    Param("port", "int", help="port on 127.0.0.1 (taken: any free one)", default=DEFAULT_PORT),
    Param("open", help="asset id or id/version to show first"),
    Param("no_browser", "bool", help="print the URL without opening a browser"),
    Param("background", "bool", help="return at once and keep serving (MCP always does)"),
)
def cmd_view(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    target = a["open"] or ""
    asset, _, version = target.partition("/")
    if asset:
        ws.asset(asset)
        if version and version not in ws.asset(asset).versions():
            raise PwError("not_found", f"{asset} has no version {version}")
    viewer = start(ws.root, a["port"])
    url = viewer.url + (f"#/{target}" if target else "")
    if not a["no_browser"]:
        webbrowser.open(url)
    if not a["background"]:
        print(f"pixelwright viewer: {url}  (Ctrl+C to stop)", file=sys.stderr)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            stop(ws.root)
    return Outcome(asset or None, version or None, data={"url": url, "port": viewer.port})
