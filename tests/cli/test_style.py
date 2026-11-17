import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from pixelwright.cli import main
from pixelwright.core.image import RGBImage
from pixelwright.core.palette import Color, Palette, Ramp, Ramps
from pixelwright.io.palette_io import read_palette, read_ramps, write_palette, write_ramps
from pixelwright.io.png import write_png

COLORS = [(20, 20, 30), (200, 60, 40), (240, 220, 160), (40, 120, 200)]


def pw(capsys: pytest.CaptureFixture[str], *argv: str, code: int = 0) -> dict[str, Any]:
    assert main([*argv, "--json"]) == code
    env: dict[str, Any] = json.loads(capsys.readouterr().out)
    return env


@pytest.fixture
def ws(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    rng = np.random.default_rng(0)
    native = np.array(COLORS, np.uint8)[rng.integers(0, 4, (12, 16))]
    rgba = np.dstack([native, np.full((12, 16), 255, np.uint8)])
    write_png(tmp_path / "src.png", RGBImage(rgba))
    write_palette(tmp_path / "scene.gpl", Palette([Color(*c) for c in COLORS]))
    root = tmp_path / "ws"
    w = ["--workspace", str(root)]
    pw(capsys, "init", "--legacy", *w)
    pw(capsys, "palette", "import", "--file", str(tmp_path / "scene.gpl"), *w)
    for asset in ("knight", "tree"):
        pw(capsys, "new", asset, "--kind", "sprite", "--palette", "palettes/scene.gpl", *w)
        pw(capsys, "attach", asset, str(tmp_path / "src.png"), *w)
        pw(capsys, "quantize", asset, *w)
    return root


def test_style_test_reports_per_asset_results(ws: Path, capsys: pytest.CaptureFixture[str]) -> None:
    w = ["--workspace", str(ws)]
    pw(capsys, "style", "bump", "--changes", '{"test_assets": ["knight", "tree"]}', *w)
    env = pw(capsys, "style", "test", *w)
    rows = env["data"]["assets"]
    assert [r["asset"] for r in rows] == ["knight", "tree"]
    for row in rows:
        assert row["version"] == "v0002" and row["results"]
        assert (ws / "assets" / row["asset"] / "versions" / "v0002" / "report.json").is_file()
    assert env["data"]["style_version"] == 3
    only = pw(capsys, "style", "test", "--assets", "tree", *w)["data"]["assets"]
    assert [r["asset"] for r in only] == ["tree"]


def test_style_test_needs_assets(ws: Path, capsys: pytest.CaptureFixture[str]) -> None:
    env = pw(capsys, "style", "test", "--workspace", str(ws), code=3)
    assert env["error"]["code"] == "invalid"


def test_style_propose_writes_palette_and_ramps(
    ws: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ref = np.zeros((4, 8, 4), np.uint8)
    ref[..., 3] = 255
    for x, (r, g, b) in enumerate([(60, 10, 10), (120, 30, 20), (200, 60, 40), (250, 140, 120)]):
        ref[:, 2 * x : 2 * x + 2, :3] = (r, g, b)
    write_png(ws / "style" / "references" / "mood.png", RGBImage(ref))
    env = pw(capsys, "style", "propose", "--colors", "4", "--workspace", str(ws))
    assert env["data"]["palette"] == "palettes/proposed.gpl"
    assert len(read_palette(ws / "style" / "palettes" / "proposed.gpl")) == 4
    ramps = read_ramps(ws / "style" / "palettes" / "proposed-ramps.yaml")
    assert ramps.palette == "proposed.gpl"
    assert "red" in env["data"]["ramps"] and len(env["data"]["ramps"]["red"]) >= 2


def test_palette_edit_rechecks_ramps(ws: Path, capsys: pytest.CaptureFixture[str]) -> None:
    w = ["--workspace", str(ws)]
    pal = ws / "style" / "palettes" / "scene.gpl"
    write_ramps(
        ws / "style" / "palettes" / "ramps.yaml", Ramps({"warm": Ramp((0, 1, 2))}, "scene.gpl")
    )
    pw(capsys, "style", "bump", "--changes", '{"ramps": "palettes/ramps.yaml"}', *w)
    env = pw(
        capsys,
        "palette",
        "edit",
        "--name",
        "scene.gpl",
        "--set",
        "3=ffffff",
        "--add",
        "102030",
        "--order",
        "4,0,1,2,3",
        *w,
    )
    colors = [c.hex for c in read_palette(pal).colors]
    assert colors == ["102030", "14141e", "c83c28", "f0dca0", "ffffff"]
    (ramp,) = env["data"]["ramps"]
    assert ramp["ramp"] == "warm" and "monotonic_lightness" in ramp
    removed = pw(capsys, "palette", "edit", "--name", "scene.gpl", "--remove", "0", "1", "2", *w)
    assert removed["data"]["colors"] == 2 and removed["warnings"]
    bad = pw(capsys, "palette", "edit", "--name", "scene.gpl", "--order", "0", *w, code=3)
    assert bad["error"]["code"] == "invalid"
