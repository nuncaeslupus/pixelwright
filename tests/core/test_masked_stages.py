import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from pixelwright.cli import main
from pixelwright.core.image import RGBImage
from pixelwright.core.palette import Color, Palette
from pixelwright.io.palette_io import write_palette
from pixelwright.io.png import read_png, write_png

COLORS = [(20, 20, 30), (200, 60, 40), (240, 220, 160), (40, 120, 200)]


def pw(capsys: pytest.CaptureFixture[str], *argv: str, code: int = 0) -> dict[str, Any]:
    assert main([*argv, "--json"]) == code
    env: dict[str, Any] = json.loads(capsys.readouterr().out)
    return env


def rgba(ws: Path, env: dict[str, Any]) -> np.ndarray:
    image = read_png(ws / env["outputs"][0])
    return image.rgba if isinstance(image, RGBImage) else image.to_rgba()


@pytest.fixture
def ws(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    rng = np.random.default_rng(1)
    # Off-palette noise everywhere, so an unmasked quantize would change every pixel.
    noise = rng.integers(0, 256, (12, 16, 3), dtype=np.uint8)
    write_png(tmp_path / "src.png", RGBImage(np.dstack([noise, np.full((12, 16), 255, np.uint8)])))
    write_palette(tmp_path / "p.gpl", Palette([Color(*c) for c in COLORS]))
    mask = np.zeros((12, 16, 4), np.uint8)
    mask[3:9, 4:12] = 255
    write_png(tmp_path / "focal.png", RGBImage(mask))
    root = tmp_path / "ws"
    w = ["--workspace", str(root)]
    pw(capsys, "init", *w)
    pw(capsys, "palette", "import", "--file", str(tmp_path / "p.gpl"), *w)
    pw(capsys, "new", "hero", "--kind", "sprite", "--palette", "palettes/p.gpl", *w)
    pw(capsys, "attach", "hero", str(tmp_path / "src.png"), *w)
    pw(capsys, "mask", "hero", "add", "--file", str(tmp_path / "focal.png"), "--id", "focal", *w)
    return root


def test_clean_with_mask_changes_nothing_outside(
    ws: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    w = ["--workspace", str(ws)]
    inside = np.zeros((12, 16), bool)
    inside[3:9, 4:12] = True
    parent = rgba(ws, {"outputs": ["assets/hero/versions/v0001/image.png"]})

    q = pw(capsys, "quantize", "hero", "--mask", "focal", *w)
    after_q = rgba(ws, q)
    assert int((after_q != parent).any(axis=2)[~inside].sum()) == 0
    assert (after_q != parent).any(axis=2)[inside].any()

    full = pw(capsys, "quantize", "hero", "--version", "v0001", *w)
    c = pw(
        capsys, "clean", "hero", "--version", full["version"], "--mask", "focal", "--resolve", *w
    )
    before_c, after_c = rgba(ws, full), rgba(ws, c)
    assert int((after_c != before_c).any(axis=2)[~inside].sum()) == 0
    assert c["data"]["resolved"] == "focal"
    (issue,) = pw(capsys, "mask", "hero", "list", *w)["data"]["masks"]
    assert issue["status"] == "fixed" and issue["fixed_in"] == c["version"]


def test_resolve_needs_a_mask(ws: Path, capsys: pytest.CaptureFixture[str]) -> None:
    env = pw(capsys, "clean", "hero", "--resolve", "--workspace", str(ws), code=3)
    assert env["error"]["code"] == "invalid"
