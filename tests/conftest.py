"""Shared fixtures. One conftest for the whole suite (mypy needs unique module names).

`ws`: an empty workspace. `workspace`, `viewer`, `browser`, `page`: the viewer end-to-end
tests (Playwright, Chromium; skipped when no browser is available)."""

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from pixelwright.app.api import AppApi
from pixelwright.app.window import STATIC
from pixelwright.asset import Asset
from pixelwright.cli import main
from pixelwright.core.image import RGBImage
from pixelwright.core.palette import Color, Palette
from pixelwright.io.palette_io import write_palette
from pixelwright.io.png import write_png
from pixelwright.project import Project, init_project
from pixelwright.viewer.server import Viewer
from pixelwright.workspace import Workspace

COLORS = [(20, 20, 30), (200, 60, 40), (240, 220, 160), (40, 120, 200)]


def pw(root: Path, *argv: str) -> None:
    assert main([*argv, "--workspace", str(root)]) == 0, argv


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    return Workspace.init(tmp_path / "ws")


@pytest.fixture
def workspace(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    """hero: v0001 attached, v0002 quantized and checked, one issue by Claude on v0002."""
    rng = np.random.default_rng(0)
    native = np.array(COLORS, np.uint8)[rng.integers(0, 4, (12, 16))]
    write_png(tmp_path / "src.png", RGBImage(np.dstack([native, np.full((12, 16), 255, np.uint8)])))
    write_palette(tmp_path / "scene.gpl", Palette([Color(*c) for c in COLORS]))
    root = tmp_path / "ws"
    pw(root, "init", "--legacy")
    pw(root, "palette", "import", "--file", str(tmp_path / "scene.gpl"))
    pw(root, "new", "hero", "--kind", "sprite", "--palette", "palettes/scene.gpl")
    pw(root, "attach", "hero", str(tmp_path / "src.png"))
    pw(root, "quantize", "hero")
    pw(root, "check", "hero")
    pw(
        root,
        "issue",
        "hero",
        "add",
        "--box",
        "2,2,4,3",
        "--rule",
        "R-PIX-3",
        "--version",
        "v0002",
        "--note",
        "stray pixels",
    )
    capsys.readouterr()
    return root


@pytest.fixture
def viewer(workspace: Path) -> Iterator[Viewer]:
    server = Viewer(workspace, 0).start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="session")
def browser() -> Iterator[Any]:
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # no browser installed on this machine
            pytest.skip(f"Chromium not available: {exc}")
        yield b
        b.close()


@pytest.fixture
def page(browser: Any, viewer: Viewer) -> Iterator[Any]:
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    pg = context.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda exc: errors.append(str(exc)))
    pg.goto(viewer.url)
    yield pg
    context.close()
    assert errors == [], errors


# --- desktop app (pywebview page driven in Chromium with the real AppApi) ---

APP_BRIDGE = """
window.pywebview = { api: new Proxy({}, { get: (_, m) => (...args) =>
  window.__pw_call(String(m), JSON.stringify(args)).then(JSON.parse) }) };
window.addEventListener("load", () => window.dispatchEvent(new Event("pywebviewready")));
"""


@pytest.fixture
def config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


@pytest.fixture
def app_project(tmp_path: Path, config_home: None) -> Project:
    project = init_project(tmp_path / "art")
    for rel, n in (("scenes/harbour", 1), ("scenes/pier", 0), ("props/crate", 1)):
        asset = Asset.create(project, rel)
        for i in range(n):
            asset.add_version(Image.new("RGBA", (32, 18), (40 * i, 60, 90, 255)))
        if n:
            asset.set_state("review")
    return project


@pytest.fixture
def open_app(browser: Any, config_home: None) -> Iterator[Callable[[AppApi], Any]]:
    contexts: list[Any] = []
    errors: list[str] = []

    def opener(api: AppApi) -> Any:
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        contexts.append(context)

        def call(method: str, args: str) -> str:
            return json.dumps(getattr(api, method)(*json.loads(args)))

        context.expose_function("__pw_call", call)
        context.add_init_script(APP_BRIDGE)
        page = context.new_page()
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto((STATIC / "index.html").as_uri())
        return page

    yield opener
    for c in contexts:
        c.close()
    assert errors == [], errors
