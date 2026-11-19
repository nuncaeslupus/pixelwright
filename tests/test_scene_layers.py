"""`pw scene layers`: a scene split into engine layers (guide `docs/guide/scene-layers.md`)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from pixelwright.asset import FINAL, Asset
from pixelwright.cli import main
from pixelwright.core import layered as ly
from pixelwright.project import init_project, load_project
from pixelwright.scene import SceneError, load_scene
from pixelwright.scene_layers import split, write_layers

WALL, FLOOR, LIT = (40, 44, 60), (90, 80, 70), (150, 90, 50)
FIRE = [(250, 190, 80), (250, 210, 90), (255, 230, 150), (255, 245, 200)]
SCENE = (
    "[scene]\nhorizon = 70\n[scene.scale]\ndoor = { y = 170, height = 60 }\n"
    '[[background]]\nasset = "scenes/fire-bg"\n'
    "[engine]\nfps = 10\n"
    "[[light]]\nat = [102, 36]\nperiod = 4\n"
    "[[light]]\nat = [240, 36]\nperiod = 6\n"
    "[[flame]]\nbox = [98, 26, 10, 16]\nheight = 10\n"
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    root = tmp_path / "game"
    init_project(root)
    bg = np.zeros((180, 320, 4), np.uint8)
    bg[..., 3] = 255
    bg[:70, :, :3], bg[70:, :, :3] = WALL, FLOOR
    bg[30:44, 90:116, :3] = LIT  # the wall lit around the torch: warm, not flame
    for row in range(12):
        bg[30 + row, 100:105, :3] = FIRE[min(3, row // 3)]
    project = load_project(root)
    Image.fromarray(bg, "RGBA").save(Asset.create(project, "scenes/fire-bg").path / FINAL)
    tomb = np.zeros((22, 44, 4), np.uint8)
    tomb[:20, 2:42] = (*WALL, 255)
    Image.fromarray(tomb, "RGBA").save(Asset.create(project, "props/tomb").path / FINAL)
    (root / "scenes").mkdir()
    (root / "scenes" / "crypt.toml").write_text(
        SCENE + '[[layer]]\nname = "tomb"\nasset = "props/tomb"\nat = [160, 140]\n'
    )
    return root


def test_layers_loop_on_the_palette_and_flames_follow_their_light(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["scene", "layers", "crypt", "--workspace", str(root), "--json"]) == 0
    env: dict[str, Any] = json.loads(capsys.readouterr().out)
    folder = root / "export" / "scenes" / "crypt-layers"
    m = json.loads((folder / "manifest.json").read_text())
    assert m["preview_frames"] == 12  # the common loop of 4 and 6
    assert m["checks"]["off_palette"] == 0 and m["checks"]["brightness_swing"] > 0
    names = [la["name"] for la in m["layers"]]
    assert names == ["flame-0", "tomb"]
    flame = m["layers"][0]
    assert flame["frames"] == 4 and flame["loop"] and flame["sheet"] == "flame-0.png"
    assert m["layers"][1]["pos"] == [138, 120]  # placed by its base, like compose
    light = m["lights"][0]["flicker"]
    assert light["follows"] == "flame-0" and len(light["curve"]) == 4
    assert m["lights"][1]["flicker"]["follows"] is None
    for name in ("background.png", "flame-0.png", "light-0.png", "light-1.png", "floor.png",
                 "preview.gif"):  # fmt: skip
        assert (folder / name).is_file()
    bg = np.asarray(Image.open(folder / "background.png"))
    assert tuple(bg[35, 102, :3]) == LIT  # the painted flame is gone, the lit wall goes on
    assert tuple(bg[35, 92, :3]) == LIT  # and the lit wall beside it was never cut
    with Image.open(folder / "preview.gif") as gif:
        assert getattr(gif, "n_frames", 1) == 12
    assert any(p.endswith("manifest.json") for p in env["outputs"])


def test_flame_frames_get_taller_and_yellower_with_their_light() -> None:
    pal = np.array([(0, 0, 0), *ly.FLAME_RAMP], np.uint8)
    curve = np.array([-1.1, 1.1])
    sprite = ly.flame_frames(6.0, 20, 12, curve, ly.nearest(pal, ly.FLAME_RAMP))
    calm, strong = (f[..., 3] > 0 for f in sprite.frames)
    assert strong.sum() > calm.sum()
    yellow = [(f[f[..., 3] > 0][:, 1].astype(float)).mean() for f in sprite.frames]
    assert yellow[1] > yellow[0]


def test_a_preview_that_cuts_a_cycle_is_refused(root: Path) -> None:
    path = root / "scenes" / "crypt.toml"
    path.write_text(path.read_text().replace("fps = 10\n", "fps = 10\nframes = 8\n"))
    with pytest.raises(SceneError, match=r"mid-loop.*12"):
        split(load_scene(load_project(root), "crypt"), load_project(root))


def test_engine_settings_and_flames_are_checked(root: Path) -> None:
    path = root / "scenes" / "crypt.toml"
    text = path.read_text()
    path.write_text(text.replace("fps = 10\n", "fsp = 10\n"))
    with pytest.raises(SceneError, match="fsp"):
        split(load_scene(load_project(root), "crypt"), load_project(root))
    path.write_text(text.replace("height = 10\n", "height = 10\nlight = 5\n"))
    with pytest.raises(SceneError, match="light"):
        load_scene(load_project(root), "crypt")


def test_snap_and_nearest_only_return_palette_colours() -> None:
    pal = np.array([(0, 0, 0), (255, 255, 255), (200, 40, 40)], np.uint8)
    rgb = np.random.default_rng(1).uniform(0, 255, (9, 7, 3))
    colours = {tuple(c) for c in ly.snap(rgb, pal).reshape(-1, 3).tolist()}
    assert colours <= {tuple(c) for c in pal.tolist()}
    assert ly.nearest(pal, [(220, 30, 30)]).tolist() == [[200, 40, 40]]


def test_curve_loops_and_light_mask_reaches_cool_areas() -> None:
    c = ly.flicker_curve(48, (0.1, 0.2, 0.3))
    nxt = ly.flicker_curve(48, (0.1 + 2 * np.pi, 0.2, 0.3))
    assert len(c) == 48 and np.allclose(c, nxt)
    img = np.zeros((40, 80, 4), np.uint8)
    img[..., :3], img[..., 3] = WALL, 255  # all cool: only the wide term lights it
    mask, peak = ly.light_mask(img, 20, 20, 80)
    assert mask.max() == pytest.approx(1.0) and peak > 0 and mask[20, 79] > 0
    assert ly.loop_length([48, 60, 40]) == 240


def test_layers_without_lights_still_export(root: Path) -> None:
    path = root / "scenes" / "crypt.toml"
    text = path.read_text()
    for block in SCENE.split("[engine]\nfps = 10\n")[1].split("[[")[1:]:
        text = text.replace("[[" + block, "")
    path.write_text(text)
    paths, manifest, _ = write_layers(load_scene(load_project(root), "crypt"),
                                      load_project(root))  # fmt: skip
    assert manifest["preview_frames"] == 1 and manifest["lights"] == []
    assert any(p.name == "tomb.png" for p in paths)
