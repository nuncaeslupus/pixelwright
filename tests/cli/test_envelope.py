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
    return tmp_path


def test_cli_json_envelope_on_every_command(
    files: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws = files / "art"
    w = ["--workspace", str(ws)]
    seen = set()

    def run(*argv: str, code: int = 0) -> dict[str, Any]:
        env = pw(capsys, *argv, *w, code=code)
        seen.add(argv[0])
        return env

    run("init")
    imp = run("palette", "import", "--file", str(files / "scene.gpl"))
    assert imp["data"]["colors"] == 4
    run("palette", "show")
    run("add", "sprites/hero", "--from", str(files / "src.png"), "--as-version")
    run("add", "sprites/hero", "--from", str(files / "src.png"))
    colors = run("colors", "sprites/hero")
    assert colors["data"]["groups"] and (ws / colors["outputs"][0]).is_file()
    checked = run("check", "sprites/hero")
    assert checked["data"]["results"]
    run("palette", "discover", "--asset", "sprites/hero", "--colors", "3", "--name", "d")
    assert run("status", "sprites/hero")["data"]["assets"]
    (ws / "replay").mkdir()
    (ws / "replay" / "a.png").write_bytes((files / "src.png").read_bytes())
    assert run("cost")["data"]["spent_usd"] == 0.0
    gen = run("generate", "sprites/hero", "--provider", "replay", "--prompt", "x", "--dry-run")
    assert gen["data"]["estimate_usd"] == 0.0
    assert "rows" in run("doctor", "--offline")["data"]
    assert run("requests")["data"]["requests"] == []
    assert run("wait", "--timeout", "0")["data"]["requests"] == []
    flow = {"normalize", "issues", "fix", "undo", "redo", "star", "finish"}
    flow |= {"open", "migrate", "bench"}  # bench: tests/bench
    assert seen | flow == set(REGISTRY)  # flow commands: test_flow_cli, test_migrate


def test_errors_use_the_envelope(files: Path, capsys: pytest.CaptureFixture[str]) -> None:
    w = ["--workspace", str(files / "nowhere")]
    assert pw(capsys, "check", "sprites/hero", *w, code=3)["error"]["code"] == "no_workspace"
    ws = ["--workspace", str(files / "art")]
    pw(capsys, "init", *ws)
    assert pw(capsys, "check", "sprites/ghost", *ws, code=3)["error"]["code"] == "no_asset"
    bad = pw(capsys, "palette", "show", "--colors", "x", *ws, code=2)
    assert bad["error"]["code"] == "usage"
