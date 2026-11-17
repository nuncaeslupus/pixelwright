from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from pixelwright.cli import main

NORMALIZE_BUDGET_S = 5.0
COLORS = [(20, 24, 33), (107, 74, 58), (233, 216, 166), (242, 165, 65), (91, 140, 133)]
FLOW_COMMANDS = {"add", "normalize", "issues", "fix", "undo", "redo", "star", "finish"}


def pw(capsys: pytest.CaptureFixture[str], root: Path, *argv: str, code: int = 0) -> dict[str, Any]:
    assert main([*argv, "--workspace", str(root), "--json"]) == code
    env: dict[str, Any] = json.loads(capsys.readouterr().out)
    return env


@pytest.fixture
def project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    root = tmp_path / "art"
    assert pw(capsys, root, "init", str(root))["ok"]
    lines = "\n".join(f"{r:3d} {g:3d} {b:3d}\tc{i}" for i, (r, g, b) in enumerate(COLORS))
    (root / "style" / "palettes" / "main.gpl").write_text(f"GIMP Palette\nName: main\n#\n{lines}\n")
    return root


@pytest.fixture
def source(tmp_path: Path) -> Path:
    """A 320x180 native image drawn at 4x, as an AI output or an upscaled sketch would be."""
    rng = np.random.default_rng(1)
    native = np.array(COLORS, np.uint8)[rng.integers(0, len(COLORS), (180, 320))]
    big = np.repeat(np.repeat(native, 4, 0), 4, 1)
    path = tmp_path / "harbour.png"
    Image.fromarray(big, "RGB").save(path)
    return path


def test_normalize_320x180_under_budget(
    project: Path, source: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pw(capsys, project, "add", "scenes/harbour", "--from", str(source))
    start = time.perf_counter()
    env = pw(capsys, project, "normalize", "scenes/harbour")
    normalize_seconds = time.perf_counter() - start
    assert normalize_seconds <= NORMALIZE_BUDGET_S
    assert env["version"] == "v001" and env["data"]["size"] == [320, 180]
    assert env["data"]["palette"] == "main" and env["warnings"] == []
    with Image.open(env["outputs"][0]) as im:
        assert im.size == (320, 180)
        rgb = np.asarray(im.convert("RGB")).reshape(-1, 3)
        assert {tuple(int(v) for v in c) for c in np.unique(rgb, axis=0)} <= set(COLORS)


def test_flow_end_to_end(
    project: Path, source: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    seen = {"init"}

    def run(*argv: str) -> dict[str, Any]:
        seen.add(argv[0])
        return pw(capsys, project, *argv)

    run("add", "scenes/harbour", "--from", str(source), "--brief", "Harbour at night")
    assert run("status")["data"]["assets"][0]["next"]["actor"] == "scripts"
    run("normalize", "scenes/harbour")
    run("check", "scenes/harbour")
    req = run("issues", "scenes/harbour", "raise", "--message", "Lamp too dim",
              "--target", "ai", "--kind", "request", "--box", "1,1,4,4")  # fmt: skip
    issue_id = req["data"]["issue"]["id"]
    assert run("status", "scenes/harbour")["data"]["assets"][0]["next"]["actor"] == "ai"

    with Image.open(project / "assets/scenes/harbour/versions/v001.png") as im:
        cand = im.convert("RGBA")
    cand.putpixel((2, 2), (*COLORS[3], 255))
    cand_path = tmp_path / "cand.png"
    cand.save(cand_path)
    fix = run("fix", "scenes/harbour", "propose", "--ids", issue_id, "--file", str(cand_path),
              "--by", "ai")  # fmt: skip
    fix_id = fix["data"]["fix"]
    run("issues", "scenes/harbour", "reply", "--id", issue_id, "--message", "Good")
    accepted = run("fix", "scenes/harbour", "accept", "--ids", fix_id)
    assert accepted["version"] == "v002"
    assert run("undo", "scenes/harbour")["version"] == "v003"
    assert run("redo", "scenes/harbour")["version"] == "v004"
    run("star", "scenes/harbour", "v001")
    done = run("finish", "scenes/harbour")
    assert Path(done["outputs"][0]) == project / "export" / "scenes" / "harbour.png"
    row = run("status")["data"]["assets"][0]
    assert row["state"] == "finished" and row["next"]["actor"] == "none"
    listed = run("issues", "scenes/harbour", "list", "--state", "all")["data"]["issues"]
    assert any(i["id"] == issue_id and i["state"] == "fixed" for i in listed)
    assert seen >= FLOW_COMMANDS


def test_errors_land_in_the_envelope(
    project: Path, source: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = pw(capsys, project, "normalize", "scenes/nothing", code=3)
    assert env["ok"] is False and env["error"]["code"] == "no_asset"
    pw(capsys, project, "add", "scenes/harbour", "--from", str(source))
    env = pw(capsys, project, "finish", "scenes/harbour", code=3)
    assert "no version" in env["error"]["message"]


def test_missing_palette_is_discovered_with_a_warning(
    project: Path, source: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (project / "style" / "palettes" / "main.gpl").unlink()
    pw(capsys, project, "add", "props/crate", "--from", str(source))
    env = pw(capsys, project, "normalize", "props/crate")
    assert env["data"]["palette"] == "own (5)"  # clean pixel art keeps its own colours
    assert any("palette" in w for w in env["warnings"])
