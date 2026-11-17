"""The game's style kit goes with every generated image."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from pixelwright.cli import main
from pixelwright.core.providers import replay
from pixelwright.core.providers.base import GenRequest

COLORS = [(20, 24, 33), (107, 74, 58), (233, 216, 166)]


def pw(capsys: pytest.CaptureFixture[str], root: Path, *argv: str) -> dict[str, Any]:
    assert main([*argv, "--workspace", str(root), "--json"]) == 0
    env: dict[str, Any] = json.loads(capsys.readouterr().out)
    return env


@pytest.fixture
def project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    root = tmp_path / "art"
    pw(capsys, root, "init")
    lines = "\n".join(f"{r} {g} {b}\tc{i}" for i, (r, g, b) in enumerate(COLORS))
    (root / "style" / "palettes" / "main.gpl").write_text(f"GIMP Palette\nName: main\n#\n{lines}\n")
    toml = root / "pixelwright.toml"
    text = toml.read_text().replace("width = 320", "width = 32")
    text = text.replace("height = 180", "height = 18")
    toml.write_text(
        text + '\n[style]\npreamble = "Moody 90s point-and-click adventure"\n'
        'rules = ["1-px dark outlines", "light from the upper left"]\n'
        '\n[style.scenes]\npreamble = "Night interiors, warm lamps"\n'
    )
    (root / "style" / "references" / "scenes").mkdir(parents=True)
    native = np.array(COLORS, np.uint8)[np.random.default_rng(1).integers(0, 3, (18, 32))]
    big = Image.fromarray(np.repeat(np.repeat(native, 4, 0), 4, 1), "RGB")
    big.save(root / "style" / "references" / "scenes" / "tavern.png")
    (root / "replay").mkdir()
    big.save(root / "replay" / "a.png")
    return root


def test_generate_sends_style_kit(
    project: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[GenRequest] = []
    real = replay.ReplayProvider.generate

    def spy(self: replay.ReplayProvider, req: GenRequest) -> Any:
        sent.append(req)
        return real(self, req)

    monkeypatch.setattr(replay.ReplayProvider, "generate", spy)
    pw(capsys, project, "add", "scenes/bar", "--from", str(project / "replay" / "a.png"))
    env = pw(capsys, project, "generate", "scenes/bar", "--provider", "replay", "--mode",
             "txt2img", "--prompt", "an empty old bar with a stage and a piano")  # fmt: skip
    (req,) = sent
    assert req.palette == ("141821", "6b4a3a", "e9d8a6")
    assert req.prompt.startswith("Night interiors, warm lamps")  # the category's preamble
    assert "32x18 pixels" in req.prompt and "#6b4a3a" in req.prompt
    assert "1-px dark outlines" in req.prompt and req.prompt.endswith("a piano")
    assert [p.name for p in req.references] == ["tavern.png"]
    assert env["data"]["versions"] == ["v001"]
    with Image.open(env["outputs"][0]) as im:  # normalised to the kit's canvas and palette
        assert im.size == (32, 18)
        assert {c for _, c in im.convert("RGB").getcolors() or []} <= set(COLORS)


def test_style_show(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    kit = pw(capsys, project, "style", "show", "scenes")["data"]
    assert kit["preamble"] == "Night interiors, warm lamps"
    assert kit["rules"] == ["1-px dark outlines", "light from the upper left"]
    assert kit["canvas"] == [32, 18] and len(kit["colors"]) == 3
    other = pw(capsys, project, "style", "show", "props")["data"]
    assert other["preamble"] == "Moody 90s point-and-click adventure"
    assert other["references"] == []
