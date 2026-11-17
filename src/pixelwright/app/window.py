"""Start the window: `pw open [folder]`."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pixelwright.app.api import AppApi

STATIC = Path(__file__).parent / "static"


def prepare_env() -> None:
    """WebKitGTK on Wayland with NVIDIA draws a blank window unless DMABUF is off."""
    if sys.platform.startswith("linux"):
        os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")


def launch(project: Path | None = None, debug: bool = False) -> None:
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError(
            "the app needs pywebview: install with `uv sync --extra app` "
            "(or `pip install 'pixelwright[app]'`)"
        ) from exc
    prepare_env()
    api = AppApi(project)
    window = webview.create_window(
        "pixelwright", url=str(STATIC / "index.html"), js_api=api, width=1280, height=800,
        min_size=(900, 600),
    )  # fmt: skip
    if window is None:
        raise RuntimeError("pywebview could not create the window")

    def pick() -> str | None:
        chosen = window.create_file_dialog(webview.FileDialog.FOLDER)
        return str(chosen[0]) if chosen else None

    api.bind_folder_picker(pick)
    webview.start(debug=debug)
