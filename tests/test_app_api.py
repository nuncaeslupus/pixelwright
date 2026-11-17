from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from pixelwright.app import recent, window
from pixelwright.app.api import AppApi
from pixelwright.asset import Asset
from pixelwright.cli import main
from pixelwright.project import Project, init_project

OPEN_BUDGET_S = 2.0


@pytest.fixture(autouse=True)
def config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    monkeypatch.setenv("APPDATA", str(home))
    return home


def _project(root: Path, n: int) -> Project:
    project = init_project(root)
    for i in range(n):
        asset = Asset.create(project, f"{('scenes', 'props')[i % 2]}/a{i:02d}")
        asset.add_version(Image.new("RGBA", (320, 180), (i, 40, 80, 255)))
    return project


def test_project_list_50_assets_under_budget(tmp_path: Path) -> None:
    project = _project(tmp_path / "art", 50)
    api = AppApi()
    start = time.perf_counter()
    assert api.open_project(str(project.root))["ok"]
    res = api.list_assets()
    open_50_assets_seconds = time.perf_counter() - start
    assert open_50_assets_seconds <= OPEN_BUDGET_S
    assert res["ok"] and len(res["assets"]) == 50
    assert res["categories"] == ["props", "scenes"]
    row = res["assets"][0]
    assert row["thumb"].startswith("data:image/png;base64,")
    assert row["next"]["actor"] == "you" and row["category"] == "props"


def test_open_from_an_image_inside_and_recent(tmp_path: Path) -> None:
    project = _project(tmp_path / "art", 1)
    api = AppApi()
    image = project.assets_dir / "scenes" / "a00" / "versions" / "v001.png"
    assert api.open_project(str(image))["project"]["path"] == str(project.root)
    assert api.recent_projects()["projects"][0]["path"] == str(project.root)


def test_errors_are_returned_not_raised(tmp_path: Path) -> None:
    api = AppApi()
    assert api.list_assets() == {"ok": False, "error": "no project is open"}
    res = api.open_project(str(tmp_path))
    assert not res["ok"] and "pixelwright.toml" in res["error"]
    assert api.pick_and_open()["ok"] is False


def test_folder_picker(tmp_path: Path) -> None:
    project = _project(tmp_path / "art", 0)
    api = AppApi()
    api.bind_folder_picker(lambda: None)
    assert api.pick_and_open() == {"ok": True, "cancelled": True}
    api.bind_folder_picker(lambda: str(project.root))
    assert api.pick_and_open()["project"]["name"] == "art"


def test_recent_keeps_order_and_limit(tmp_path: Path) -> None:
    roots = []
    for i in range(recent.LIMIT + 2):
        root = tmp_path / f"p{i}"
        root.mkdir()
        roots.append(root)
        recent.remember(root)
    recent.remember(roots[3])
    got = recent.load_recent()
    assert got[0] == str(roots[3].resolve()) and len(got) == recent.LIMIT


def test_dmabuf_default_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEBKIT_DISABLE_DMABUF_RENDERER", raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    window.prepare_env()
    import os

    assert os.environ["WEBKIT_DISABLE_DMABUF_RENDERER"] == "1"


def test_pw_open_hands_the_project_to_the_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path / "art", 1)
    seen: dict[str, Any] = {}
    monkeypatch.setattr(window, "launch", lambda p, debug=False: seen.update(project=p))
    image = project.assets_dir / "scenes" / "a00" / "versions" / "v001.png"
    assert main(["open", str(image), "--json"]) == 0
    json.loads(capsys.readouterr().out)
    assert seen["project"] == project.root
    assert main(["open", str(tmp_path / "nowhere"), "--json"]) == 3
