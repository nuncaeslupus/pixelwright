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
from pixelwright.viewer import command as view_command

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


def test_cli_json_envelope_on_every_command(
    files: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws = files / "ws"
    w = ["--workspace", str(ws)]
    seen = set()

    def run(*argv: str, code: int = 0) -> dict[str, Any]:
        env = pw(capsys, *argv, *w, code=code)
        seen.add(argv[0])
        return env

    run("init", "--canvas", "16x12")
    imp = run("palette", "import", "--file", str(files / "scene.gpl"))
    assert imp["data"]["colors"] == 4
    run("new", "hero", "--kind", "sprite", "--palette", "palettes/scene.gpl")
    src = run("attach", "hero", str(files / "src.png"))
    assert src["version"] == "v0001"
    run("attach", "hero", str(files / "src.png"), "--as", "ref")
    snapped = run("snap", "hero")
    assert snapped["data"]["scale"] == 4 and snapped["version"] == "v0002"
    run("mask", "hero", "add", "--file", str(files / "focal.png"), "--id", "focal")
    assert len(run("mask", "hero", "list")["data"]["masks"]) == 1
    q = run("quantize", "hero")
    assert q["data"]["mean_error"] == 0.0
    run("clean", "hero", "--mask", "focal")
    checked = run("check", "hero", "--mask", "focal")
    assert checked["outputs"][0].endswith("report.json") and checked["data"]["results"]
    for view in ("upscale", "gray", "values", "silhouette", "overlay"):
        assert (ws / run("render", "hero", "--view", view)["outputs"][0]).is_file()
    assert run("diff", "hero", "v0003", "v0004")["data"]["changed"] >= 0
    run("export", "hero", code=3)  # nothing approved yet
    run("reject", "hero", "v0003", "--note", "noisy")
    assert run("approve", "hero", "v0004")["stage"] == "approved"
    exported = run("export", "hero")
    assert exported["stage"] == "final" and (ws / exported["outputs"][0]).is_file()
    run("palette", "discover", "--asset", "hero", "--colors", "3", "--name", "d.gpl")
    run("palette", "show")
    bumped = run("style", "bump", "--changes", '{"notes": "dusk"}')
    assert bumped["data"]["stale"]
    run("style", "show")
    (ws / "experiments" / "try.png").write_bytes(b"x")
    assert run("prune")["data"]["removed"] == ["experiments/try.png"]
    run("issue", "hero", "add", "--box", "0,0,2,2", "--rule", "R-PIX-3")
    assert len(run("issue", "hero", "list")["data"]["issues"]) == 2
    run("issue", "hero", "resolve", "--id", "r-pix-3-1")
    assert run("status", "hero")["data"]["assets"][0]["open_issues"] == 1
    assert run("history", "hero")["data"]["history"]
    assert run("cost")["data"]["spent_usd"] == 0.0
    gen = run("generate", "hero", "--provider", "replay", "--prompt", "x", "--dry-run")
    assert gen["data"]["estimate_usd"] == 0.0
    assert "rows" in run("doctor", "--offline")["data"]
    assert run("next", "hero")["data"]["step"]
    assert run("tour", "--path", str(files / "tour"), "--no-view")["stage"] == "final"
    assert run("inbox")["data"]["count"] >= 0
    crit = files / "critique.md"
    crit.write_text(
        "---\nschema: pixelwright/critique@1\nversion: v0004\nverdict: fine\n---\n"
        "## Focal area\nissue: focal\nrule: R-VAL-1\n\nReads well.\n"
    )
    run("critique", "hero", "write", "--version", "v0004", "--file", str(crit))
    shown = run("critique", "hero", "show", "--version", "v0004")["data"]
    assert shown["complaints"][0]["issue"] == "focal"
    run("mask", "hero", "clear")
    viewed = run("view", "--open", "hero/v0004", "--port", "0", "--background", "--no-browser")
    assert viewed["data"]["url"].endswith("/#/hero/v0004")
    view_command.stop(ws.resolve())
    assert seen == set(REGISTRY)


def test_errors_use_the_envelope(files: Path, capsys: pytest.CaptureFixture[str]) -> None:
    w = ["--workspace", str(files / "nowhere")]
    assert pw(capsys, "snap", "hero", *w, code=3)["error"]["code"] == "no_workspace"
    assert pw(capsys, "new", "hero", "--kind", "dragon", *w, code=2)["error"]["code"] == "usage"
    ws = ["--workspace", str(files / "ws")]
    pw(capsys, "init", *ws)
    assert pw(capsys, "snap", "ghost", *ws, code=3)["error"]["code"] == "not_found"
    assert pw(capsys, "new", "Bad_Id", "--kind", "prop", *ws, code=3)["error"]["code"] == "invalid"
