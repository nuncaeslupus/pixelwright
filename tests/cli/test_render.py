import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage

from pixelwright.cli import main
from pixelwright.core.image import RGBImage
from pixelwright.io.aseprite import AseDocument, Cel, Frame, Layer, flatten_frames, write_aseprite
from pixelwright.io.png import write_png
from pixelwright.workspace import Workspace


def pw(capsys: pytest.CaptureFixture[str], *argv: str) -> dict:  # type: ignore[type-arg]
    code = main([*argv, "--json"])
    env = json.loads(capsys.readouterr().out)
    assert code == 0, env
    return env  # type: ignore[no-any-return]


def _sprite(tmp_path: Path) -> Path:
    rgba = np.zeros((6, 8, 4), np.uint8)
    rgba[1:5, 2:6] = (200, 40, 40, 255)
    rgba[2:4, 3:5] = (30, 30, 200, 255)
    write_png(tmp_path / "hero.png", RGBImage(rgba))
    return tmp_path / "hero.png"


def _doc(frames: int) -> AseDocument:
    out = []
    for f in range(frames):
        px = np.zeros((6, 8, 4), np.uint8)
        px[f : f + 2, 1:4] = (10 * f, 200, 50, 255)
        chunks: list = [Layer("body")] if f == 0 else []  # type: ignore[type-arg]
        out.append(Frame(duration=80 + 20 * f, chunks=[*chunks, Cel(0, pixels=px)]))
    return AseDocument(8, 6, frames=out)


@pytest.fixture
def ws(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    root = tmp_path / "ws"
    pw(capsys, "init", "--legacy", str(root), "--canvas", "8x6")
    pw(capsys, "new", "hero", "--kind", "sprite", "--workspace", str(root))
    pw(capsys, "attach", "hero", str(_sprite(tmp_path)), "--workspace", str(root))
    return root


def test_init_accepts_positional_path(ws: Path) -> None:
    assert (ws / "pixelwright.toml").is_file()


def test_flatten_frames_composites_visible_layers() -> None:
    [(first, ms), _] = flatten_frames(_doc(2))
    assert ms == 80 and first[0, 1].tolist() == [0, 200, 50, 255] and first[5, 7, 3] == 0


def test_render_gif_matches_frame_count_and_durations(
    ws: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_aseprite(ws / "assets" / "hero" / "versions" / "v0001" / "image.aseprite", _doc(3))
    env = pw(capsys, "render", "hero", "--view", "gif", "--scale", "2", "--workspace", str(ws))
    assert env["data"]["frames"] == 3 and env["data"]["durations"] == [80, 100, 120]
    with PILImage.open(ws / env["outputs"][0]) as gif:
        assert getattr(gif, "n_frames", 1) == 3 and gif.size == (16, 12)
    apng = pw(capsys, "render", "hero", "--view", "apng", "--workspace", str(ws))
    assert (ws / apng["outputs"][0]).suffix == ".png"


def test_palette_discover_asset_sets_asset_palette(
    ws: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pw(capsys, "palette", "discover", "--asset", "hero", "--colors", "3", "--workspace", str(ws))
    spec = Workspace.open(ws).asset("hero").spec()
    assert spec["palette"] == "style:palettes/hero.gpl"


def test_grid_check_runs_on_an_upscaled_export(
    ws: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    big = np.repeat(np.repeat(np.asarray(PILImage.open(_sprite(tmp_path))), 3, 0), 3, 1)
    write_png(tmp_path / "big.png", RGBImage(big))
    argv = ["check", "hero", "--checks", "grid", "--file", str(tmp_path / "big.png")]
    env = pw(capsys, *argv, "--scale", "3", "--workspace", str(ws))
    assert env["data"]["results"][0] == {"check": "grid", "status": "pass", "value": 0.0}
