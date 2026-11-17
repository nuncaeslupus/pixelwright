"""The game's style kit goes with every generated image."""

from __future__ import annotations

import json
import shutil
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
    assert "32x18 pixels" in req.prompt and "#" not in req.prompt  # the palette goes as palette
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


def test_preamble_is_a_sentence_and_inputs_folder_is_made(
    project: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[GenRequest] = []
    real = replay.ReplayProvider.generate

    def spy(self: replay.ReplayProvider, req: GenRequest) -> Any:
        sent.append(req)
        return real(self, req)

    monkeypatch.setattr(replay.ReplayProvider, "generate", spy)
    toml = project / "pixelwright.toml"
    toml.write_text(toml.read_text() + '\n[presets.replay]\npreamble = "VGA era look"\n')
    pw(capsys, project, "add", "scenes/bar", "--from", str(project / "replay" / "a.png"))
    shutil.rmtree(project / "assets" / "scenes" / "bar" / "inputs")
    pw(capsys, project, "generate", "scenes/bar", "--provider", "replay", "--mode",
       "txt2img", "--prompt", "A cosy tavern")  # fmt: skip
    assert sent[0].prompt.startswith("VGA era look. Night interiors, warm lamps.")


def test_colors_setting_discovers_the_palette(
    project: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    rng = np.random.default_rng(3)
    native = rng.integers(0, 256, (18, 32, 3), np.uint8)  # far more than 40 colours
    Image.fromarray(np.repeat(np.repeat(native, 4, 0), 4, 1), "RGB").save(tmp_path / "n.png")
    pw(capsys, project, "add", "scenes/noisy", "--from", str(tmp_path / "n.png"))
    (project / "assets" / "scenes" / "noisy" / "asset.toml").write_text(
        'state = "processing"\ncolors = 40\n'
    )
    env = pw(capsys, project, "normalize", "scenes/noisy")
    with Image.open(env["outputs"][0]) as im:
        assert 16 < len(im.convert("RGB").getcolors() or []) <= 40
    shown = pw(capsys, project, "style", "show", "scenes/noisy")["data"]
    assert shown["colors"] == [] and shown["max_colors"] == 40


def test_prompt_names_palette_size_without_codes(project: Path) -> None:
    from pixelwright.project import load_project
    from pixelwright.style import style_kit

    kit = style_kit((load_project(project), "scenes"))
    words = kit.prompt(4)
    assert "#" not in words and "about 3 colours" in words


def test_palette_discover_from_images_writes_swatch(
    project: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    other = tmp_path / "b.png"
    Image.new("RGB", (32, 18), (200, 40, 40)).save(other)
    first = str(project / "replay" / "a.png")
    env = pw(capsys, project, "palette", "discover", "--images", first, str(other),
             "--colors", "4", "--name", "cast", "--swatch")  # fmt: skip
    swatch = project / "style" / "references" / "palette-cast.png"
    assert str(swatch) in env["outputs"]
    found = {tuple(c[:3]) for c in np.asarray(Image.open(swatch)).reshape(-1, 4) if c[3]}
    assert (200, 40, 40) in found and len(found) == env["data"]["colors"]


def test_palette_ramps_from_keys(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    env = pw(capsys, project, "palette", "ramps", "--preset", "none", "--keys", "wood=8a5a3a",
             "moss=5a8a3a", "--steps", "3", "--name", "r", "--swatch")  # fmt: skip
    assert env["data"]["colors"] == 3 * 2 + 2
    swatch = Image.open(project / "style" / "references" / "palette-r.png")
    assert swatch.size == (3 * 24, 3 * 24)  # a ramp per row, then the ends


def test_palette_ramps_from_images(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    image = str(project / "replay" / "a.png")
    env = pw(capsys, project, "palette", "ramps", "--images", image, "--colors", "2",
             "--steps", "3", "--name", "f")  # fmt: skip
    assert 3 <= env["data"]["colors"] <= 2 * 3 + 2  # no adventure preset with images
