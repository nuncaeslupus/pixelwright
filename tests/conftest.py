"""Shared fixtures. One conftest for the whole suite (mypy needs unique module names).

`browser`, `app_project`, `open_app`: the app end-to-end tests (Playwright, Chromium;
skipped when no browser is available)."""

import json
import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from pixelwright.app.api import AppApi
from pixelwright.app.window import STATIC
from pixelwright.asset import Asset
from pixelwright.project import Project, init_project


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


# --- desktop app (pywebview page driven in Chromium with the real AppApi) ---

APP_BRIDGE = """
window.pywebview = { api: new Proxy({}, { get: (_, m) => (...args) =>
  window.__pw_call(String(m), JSON.stringify(args)).then(JSON.parse) }) };
window.addEventListener("load", () => window.dispatchEvent(new Event("pywebviewready")));
"""


@pytest.fixture
def config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))


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


@pytest.fixture(autouse=True)
def _no_provider_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never see real API keys from the environment (PW_<NAME>_KEY)."""
    for name in list(os.environ):
        if name.startswith("PW_") and name.endswith("_KEY"):
            monkeypatch.delenv(name)
