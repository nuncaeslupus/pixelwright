import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from pixelwright.cli import REGISTRY, main
from pixelwright.core.image import RGBImage
from pixelwright.core.palette import Color, Palette
from pixelwright.io.palette_io import write_palette
from pixelwright.io.png import write_png

OK_KEYS = {
    "ok",
    "command",
    "asset",
    "version",
    "stage",
    "outputs",
    "data",
    "warnings",
    "duration_ms",
}
COLORS = [(20, 20, 30), (200, 60, 40), (240, 220, 160), (40, 120, 200)]


def validate(env: Any) -> None:
    assert isinstance(env, dict) and isinstance(env["ok"], bool)
    assert isinstance(env["duration_ms"], int) and env["command"] in REGISTRY
    if env["ok"]:
        assert set(env) == OK_KEYS
        assert isinstance(env["outputs"], list) and isinstance(env["warnings"], list)
        assert isinstance(env["data"], dict)
        for key in ("asset", "version", "stage"):
            assert env[key] is None or isinstance(env[key], str)
    else:
        assert set(env["error"]) == {"code", "message", "details"}


def pw(capsys: pytest.CaptureFixture[str], *argv: str, code: int = 0) -> dict[str, Any]:
    assert main([*argv, "--json"]) == code
    env: dict[str, Any] = json.loads(capsys.readouterr().out)
    validate(env)
    return env


@pytest.fixture
def files(tmp_path: Path) -> Path:
    rng = np.random.default_rng(0)
    native = np.array(COLORS, np.uint8)[rng.integers(0, 4, (12, 16))]
    big = np.repeat(np.repeat(native, 4, 0), 4, 1)
    rgba = np.dstack([big, np.full(big.shape[:2], 255, np.uint8)])
    write_png(tmp_path / "src.png", RGBImage(rgba))
    write_palette(tmp_path / "scene.gpl", Palette([Color(*c) for c in COLORS]))
    mask = np.zeros((12, 16, 4), np.uint8)
    mask[3:9, 4:12] = 255
    write_png(tmp_path / "focal.png", RGBImage(mask))
    (tmp_path / "exp").mkdir()
    return tmp_path


def test_diff_reports_check_deltas_and_changed_area(
    files: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    w = ["--workspace", str(files / "ws")]
    pw(capsys, "init", "--canvas", "16x12", *w)
    pw(capsys, "palette", "import", "--file", str(files / "scene.gpl"), *w)
    pw(capsys, "new", "hero", "--kind", "sprite", "--palette", "palettes/scene.gpl", *w)
    pw(capsys, "attach", "hero", str(files / "src.png"), *w)
    pw(capsys, "snap", "hero", *w)
    pw(capsys, "quantize", "hero", *w)
    main(["check", "hero", *w, "--json"])  # exit code depends on the findings
    capsys.readouterr()
    pw(capsys, "mask", "hero", "add", "--file", str(files / "focal.png"), "--id", "focal", *w)
    pw(capsys, "clean", "hero", "--mask", "focal", *w)
    data = pw(capsys, "diff", "hero", "v0003", "v0004", *w)["data"]
    assert len(data["colors"]) == 2 and all(c >= 1 for c in data["colors"])
    rows = {r["check"]: r for r in data["checks"]}
    assert rows and all(r["a"] is not None and r["b"] is None for r in rows.values())
    assert data["changed"] == 0 or len(data["bbox"]) == 4
