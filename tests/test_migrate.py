from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from pixelwright.asset import open_asset
from pixelwright.cli import main
from pixelwright.issues import IssueLog
from pixelwright.project import load_project

OLD_ISSUES = """\
masks:
  - id: r-pix-3-1
    box: [2, 2, 4, 3]
    rule: R-PIX-3
    version: v0002
    author: claude
    status: open
    note: stray pixels
"""


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """An M0-M3 workspace as it lay on disk: hero with two versions and one issue."""
    root = tmp_path / "ws"
    hero = root / "assets" / "hero"
    (root / "style" / "palettes").mkdir(parents=True)
    (root / "style" / "palettes" / "scene.gpl").write_text("GIMP Palette\n0 0 0 black\n")
    (root / "pixelwright.toml").write_text("[canvas]\nwidth = 16\nheight = 12\n")
    rng = np.random.default_rng(0)
    for i in (1, 2):
        (hero / "versions" / f"v000{i}").mkdir(parents=True)
        pixels = rng.integers(0, 255, (12, 16, 4), np.uint8)
        Image.fromarray(pixels, "RGBA").save(hero / "versions" / f"v000{i}" / "image.png")
    (hero / "asset.yaml").write_text("id: hero\nkind: sprite\npalette: style:palettes/scene.gpl\n")
    (hero / "masks").mkdir()
    (hero / "masks" / "masks.yaml").write_text(OLD_ISSUES)
    return root


def pw(capsys: pytest.CaptureFixture[str], root: Path, *argv: str, code: int = 0) -> dict[str, Any]:
    assert main([*argv, "--workspace", str(root), "--json"]) == code
    env: dict[str, Any] = json.loads(capsys.readouterr().out)
    return env


def test_migrate_m3_workspace_preserves_versions(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old_versions = ["v0001", "v0002"]
    old_dir = workspace / "assets" / "hero" / "versions"
    old_pixels = [np.asarray(Image.open(old_dir / v / "image.png")) for v in old_versions]
    env = pw(capsys, workspace, "migrate")
    assert env["data"]["assets"] == {"hero": "sprites/hero"}
    assert (workspace / "pixelwright.toml.bak").is_file() and (workspace / "assets.bak").is_dir()

    project = load_project(workspace)
    asset = open_asset(project, project.assets_dir / "sprites" / "hero")
    assert asset.versions() == [f"v{i:03d}" for i in range(1, len(old_versions) + 1)]
    for version, pixels in zip(asset.versions(), old_pixels, strict=True):
        with Image.open(asset.version_path(version)) as im:
            assert np.array_equal(np.asarray(im.convert("RGBA")), pixels)
    assert asset.settings().palette == "scene"
    issues = list(IssueLog(asset).state().issues.values())
    assert [(i.message, i.version, i.author) for i in issues] == [("stray pixels", "v002", "ai")]
    assert pw(capsys, workspace, "status")["data"]["assets"][0]["state"] == "review"


def test_migrate_refuses_a_v2_project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pw(capsys, tmp_path / "art", "init")
    env = pw(capsys, tmp_path / "art", "migrate", code=3)
    assert env["error"]["code"] == "exists"
