"""Scenes in layers: scale from the ground plane, compose, shadows, sizes, states."""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from pixelwright.asset import FINAL, Asset
from pixelwright.cli import main
from pixelwright.core.providers import replay
from pixelwright.core.providers.base import GenRequest
from pixelwright.project import init_project, load_project
from pixelwright.scene import compose, load_scene, scene_prompt, suggested_sizes

FLOOR, WALL = (90, 80, 70), (40, 44, 60)
DARK_FLOOR = (50, 44, 38)
STONE, RED, BLUE = (150, 150, 160), (200, 40, 40), (40, 40, 200)


def pw(capsys: pytest.CaptureFixture[str], root: Path, *argv: str) -> dict[str, Any]:
    assert main([*argv, "--workspace", str(root), "--json"]) == 0
    env: dict[str, Any] = json.loads(capsys.readouterr().out)
    return env


def _asset(root: Path, rel: str, img: np.ndarray) -> None:
    project = load_project(root)
    asset = Asset.create(project, rel)
    Image.fromarray(img, "RGBA").save(asset.path / FINAL)


def _figure(w: int, h: int, color: tuple[int, int, int], pad: int = 2) -> np.ndarray:
    img = np.zeros((h + pad, w + 2 * pad, 4), np.uint8)
    img[:h, pad : pad + w] = (*color, 255)  # transparent padding below and on the sides
    return img


@pytest.fixture
def root(tmp_path: Path) -> Path:
    root = tmp_path / "game"
    init_project(root)
    bg = np.zeros((180, 320, 4), np.uint8)
    bg[:70] = (*WALL, 255)
    bg[70:] = (*FLOOR, 255)
    bg[175:, :4] = (*DARK_FLOOR, 255)  # a darker floor colour the shadow can use
    _asset(root, "scenes/crypt-bg", bg)
    _asset(root, "props/tomb", _figure(40, 20, STONE))
    f1 = np.concatenate([np.zeros((6, 44, 4), np.uint8), _figure(40, 20, STONE)])
    f2 = f1.copy()
    f2[0:4, 2:42] = (*STONE, 255)  # frame 2: the lid lifted above the box
    f2[6:10] = 0
    strip = np.concatenate([f1, f2], axis=1)
    _asset(root, "props/tomb-open", strip)
    _asset(root, "chars/knight", _figure(10, 51, RED))
    _asset(root, "chars/knight-s", _figure(6, 26, BLUE))
    (root / "scenes").mkdir()
    (root / "scenes" / "crypt.toml").write_text(
        '[scene]\nhorizon = 70\ncamera = "frontal"\n'
        "[scene.scale]\ndoor = { y = 170, height = 60 }\n"
        '[[background]]\nasset = "scenes/crypt-bg"\n'
        '[[layer]]\nname = "tomb"\nasset = "props/tomb"\nat = [160, 140]\n'
        'states = { open = "props/tomb-open" }\nframes = { open = 2 }\n'
        '[[layer]]\nname = "knight"\nsizes = ["chars/knight", "chars/knight-s"]\nat = [60, 170]\n'
    )
    return root


def test_person_height_follows_horizon(root: Path) -> None:
    scene = load_scene(load_project(root), "crypt")
    assert scene.person_height(170) == pytest.approx(51.0)
    assert scene.person_height(120) == pytest.approx(25.5)
    assert scene.person_height(70) == pytest.approx(0.0)


def test_shadow_uses_scene_colours(root: Path) -> None:
    project = load_project(root)
    out = compose(load_scene(project, "crypt"), project)
    colours = {tuple(c) for c in out.image[..., :3].reshape(-1, 3)}
    assert colours <= {FLOOR, WALL, DARK_FLOOR, STONE, RED, BLUE}
    # just past the sides of the tomb base (row 139) the floor is in shadow
    assert tuple(out.image[139, 160 - 22, :3]) == DARK_FLOOR
    assert tuple(out.image[139, 100, :3]) == FLOOR
    plain = compose(load_scene(project, "crypt"), project, shadows=False)
    assert tuple(plain.image[139, 160 - 22, :3]) != DARK_FLOOR


def test_layers_placed_by_base_far_to_near(root: Path) -> None:
    project = load_project(root)
    out = compose(load_scene(project, "crypt"), project)
    tomb = next(p for p in out.placed if p.name == "tomb")
    assert [p.name for p in out.placed] == ["tomb", "knight"]  # row 140 is farther than 170
    assert tomb.y + 20 == 140  # the opaque base sits on row 140, not the padding
    assert tuple(out.image[139, 160, :3]) == STONE and tuple(out.image[140, 160, :3]) != STONE


def test_actor_size_picked_by_depth_without_resampling(root: Path) -> None:
    project = load_project(root)
    near = compose(load_scene(project, "crypt"), project)
    knight = next(p for p in near.placed if p.name == "knight")
    assert knight.asset == "chars/knight" and not near.warnings
    text = (root / "scenes" / "crypt.toml").read_text().replace("at = [60, 170]", "at = [60, 120]")
    (root / "scenes" / "crypt.toml").write_text(text)
    far = compose(load_scene(project, "crypt"), project)
    small = next(p for p in far.placed if p.name == "knight")
    assert small.asset == "chars/knight-s"
    region = far.image[small.y : small.y + small.height, small.x : small.x + small.width]
    assert int((region[..., :3] == BLUE).all(-1).sum()) == 6 * 26  # pixel for pixel


def test_size_warning_and_suggested_sizes(root: Path) -> None:
    project = load_project(root)
    text = (root / "scenes" / "crypt.toml").read_text().replace("at = [60, 170]", "at = [60, 145]")
    (root / "scenes" / "crypt.toml").write_text(text)
    scene = load_scene(project, "crypt")
    assert any("draw a size near 38" in w for w in compose(scene, project).warnings)
    sizes = suggested_sizes(scene, near_y=170, far_y=110)
    assert sizes[0] == 51 and sizes[-1] <= 20 * 1.15
    assert all(b < a for a, b in itertools.pairwise(sizes))


def test_state_switch_and_frames(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = load_project(root)
    scene = load_scene(project, "crypt")
    closed = compose(scene, project).image
    opened = compose(scene, project, states={"tomb": "open"}, frame=1).image
    changed = np.nonzero((closed != opened).any(-1))
    assert changed[1].min() >= 160 - 25 and changed[1].max() <= 160 + 25  # only the tomb
    env = pw(capsys, root, "scene", "compose", "crypt", "--state", "tomb=open", "--gif")
    gif = next(p for p in env["outputs"] if p.endswith(".gif"))
    with Image.open(gif) as im:
        assert getattr(im, "n_frames", 1) == 2
    layout = json.loads(Path(next(p for p in env["outputs"] if p.endswith(".json"))).read_text())
    assert [la["name"] for la in layout["layers"]] == ["tomb", "knight"]


def test_scene_prompt_follows_eye_level(root: Path) -> None:
    scene = load_scene(load_project(root), "crypt")
    assert "front" in scene_prompt(scene, 140, height=20) and "top surface" in scene_prompt(
        scene, 140, 20
    )
    assert "crosses it at 50%" in scene_prompt(scene, 140, height=140)
    assert "51 px tall" in scene_prompt(scene, 170)


def test_generate_scene_adds_camera_and_size(
    root: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[GenRequest] = []
    real = replay.ReplayProvider.generate

    def spy(self: replay.ReplayProvider, req: GenRequest) -> Any:
        sent.append(req)
        return real(self, req)

    monkeypatch.setattr(replay.ReplayProvider, "generate", spy)
    (root / "replay").mkdir()
    Image.new("RGB", (320, 180), FLOOR).save(root / "replay" / "a.png")
    pw(capsys, root, "add", "props/urn", "--from", str(root / "replay" / "a.png"))
    pw(capsys, root, "generate", "props/urn", "--provider", "replay", "--mode", "txt2img",
       "--prompt", "a stone urn", "--scene", "crypt", "--at", "150", "--height", "30")  # fmt: skip
    (req,) = sent
    assert "a stone urn" in req.prompt and "frontal camera" in req.prompt
    assert "About 30 px tall" in req.prompt and "person beside it would be 41 px" in req.prompt


def test_scene_new_and_scale_cli(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pw(capsys, root, "scene", "new", "hall", "--background", "scenes/crypt-bg",
       "--horizon", "60", "--door", "160:50")  # fmt: skip
    env = pw(capsys, root, "scene", "scale", "hall", "--at", "160")
    assert env["data"]["person"] == pytest.approx(42.5)
    assert pw(capsys, root, "scene", "show", "hall")["data"]["camera"] == "frontal"


HEAD = "[scene]\nhorizon = 70\n[scene.scale]\ndoor = { y = 170, height = 60 }\n"
BG = '[[background]]\nasset = "scenes/crypt-bg"\n'


@pytest.mark.parametrize(
    "text",
    [
        HEAD + "[[background]]\nx = 0\n",  # no asset
        "[scene]\nhorizon = 70\n[scene.scale]\nperson = 5\n" + BG,  # not a table
        HEAD + BG + '[[layer]]\nname = "t"\nasset = "a"\nat = [1, 1]\nframes = 3\n',
    ],
)
def test_malformed_scene_is_a_clear_error(
    root: Path, capsys: pytest.CaptureFixture[str], text: str
) -> None:
    (root / "scenes" / "crypt.toml").write_text(text)
    assert main(["scene", "show", "crypt", "--workspace", str(root), "--json"]) != 0
    assert json.loads(capsys.readouterr().out)["error"]["code"]


def test_prompt_at_horizon_and_bad_new_leave_nothing(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["scene", "prompt", "crypt", "--at", "70", "--workspace", str(root), "--json"]) != 0
    capsys.readouterr()
    argv = [
        "scene",
        "new",
        "bad",
        "--background",
        "scenes/crypt-bg",
        "--horizon",
        "100",
        "--door",
        "90:50",
    ]
    assert main([*argv, "--workspace", str(root), "--json"]) != 0
    assert not (root / "scenes" / "bad.toml").exists()
