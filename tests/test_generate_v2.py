from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from pixelwright.budget import Ledger
from pixelwright.cli import main

COLORS = [(20, 24, 33), (107, 74, 58), (233, 216, 166), (242, 165, 65), (91, 140, 133)]


def pw(capsys: pytest.CaptureFixture[str], root: Path, *argv: str, code: int = 0) -> dict[str, Any]:
    assert main([*argv, "--workspace", str(root), "--json"]) == code
    env: dict[str, Any] = json.loads(capsys.readouterr().out)
    return env


def _painting(path: Path, seed: int) -> Path:
    native = np.array(COLORS, np.uint8)[np.random.default_rng(seed).integers(0, 5, (18, 32))]
    Image.fromarray(np.repeat(np.repeat(native, 4, 0), 4, 1), "RGB").save(path)
    return path


@pytest.fixture
def project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    root = tmp_path / "art"
    pw(capsys, root, "init")
    lines = "\n".join(f"{r} {g} {b}\tc{i}" for i, (r, g, b) in enumerate(COLORS))
    (root / "style" / "palettes" / "main.gpl").write_text(f"GIMP Palette\nName: main\n#\n{lines}\n")
    toml = root / "pixelwright.toml"
    text = toml.read_text().replace("width = 320", "width = 32")
    toml.write_text(text.replace("height = 180", "height = 18"))
    (root / "replay").mkdir()
    _painting(root / "replay" / "a.png", 1)
    return root


def test_generate_adds_inputs_and_versions(
    project: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    pw(capsys, project, "add", "scenes/harbour", "--from", str(_painting(tmp_path / "s.png", 2)))
    dry = pw(capsys, project, "generate", "scenes/harbour", "--provider", "replay",
             "--prompt", "harbour", "--dry-run")  # fmt: skip
    assert dry["data"]["estimate_usd"] == 0.0 and dry["data"]["versions"] == []
    env = pw(capsys, project, "generate", "scenes/harbour", "--provider", "replay",
             "--prompt", "harbour")  # fmt: skip
    assert env["data"]["versions"] == ["v001"] and env["data"]["mode"] == "img2img"
    assert len(list((project / "assets/scenes/harbour/inputs").iterdir())) == 2
    with Image.open(env["outputs"][0]) as im:
        assert im.size == (32, 18)
    rows = Ledger(project).rows()
    assert len(rows) == 1 and rows[0]["asset"] == "scenes/harbour"
    assert pw(capsys, project, "cost")["data"]["calls"] == 1


def test_generate_issue_proposes_a_fix_inside_its_areas(
    project: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    pw(capsys, project, "add", "scenes/harbour", "--from", str(_painting(tmp_path / "s.png", 2)))
    pw(capsys, project, "normalize", "scenes/harbour")
    issue = pw(capsys, project, "issues", "scenes/harbour", "raise", "--message", "redo the boat",
               "--box", "2,3,5,4")["data"]["issue"]["id"]  # fmt: skip
    env = pw(capsys, project, "generate", "scenes/harbour", "--provider", "replay",
             "--issue", issue)  # fmt: skip
    assert env["data"]["fix"]
    with (
        Image.open(project / "assets/scenes/harbour/versions/v001.png") as a,
        Image.open(env["outputs"][0]) as b,
    ):
        diff = (np.asarray(a.convert("RGBA")) != np.asarray(b.convert("RGBA"))).any(axis=-1)
    outside = diff.copy()
    outside[3:7, 2:7] = False
    assert not outside.any()
    listed = pw(capsys, project, "issues", "scenes/harbour")["data"]["issues"]
    assert listed[0]["fixes"] == [env["data"]["fix"]]
