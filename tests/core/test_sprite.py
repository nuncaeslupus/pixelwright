"""Sprites on a flat background: keyed out, framed and reduced keeping outlines."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from pixelwright.cli import main
from pixelwright.core.image import RGBImage
from pixelwright.core.sprite import background
from pixelwright.io.png import read_png, write_png

MAGENTA = (203, 52, 108)


def _sprite() -> np.ndarray:
    """1024x1024: noisy magenta, a 460 px tall figure with a 6 px dark outline, a red
    cape and a soft shadow-free edge, as an image model paints it."""
    rng = np.random.default_rng(2)
    rgb = np.zeros((1024, 1024, 3))
    rgb[...] = MAGENTA
    rgb += rng.normal(0, 4, rgb.shape)
    rgb[300:760, 420:600] = (20, 18, 24)  # outline
    rgb[306:754, 426:594] = (150, 155, 165)  # armour
    rgb[400:740, 432:470] = (170, 40, 45)  # red cape
    rgb[330:350, 480:540] = (240, 230, 120)  # visor glint
    return np.clip(rgb, 0, 255).astype(np.uint8)


def test_scenes_have_no_flat_background() -> None:
    rng = np.random.default_rng(0)
    scene = rng.integers(0, 255, (200, 300, 3), np.uint8)
    assert background(RGBImage.from_array(scene)) is None
    assert background(RGBImage.from_array(_sprite())) is not None


def test_sprite_background_keyed_and_figure_framed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_png(tmp_path / "knight.png", RGBImage.from_array(_sprite()))
    art = ["--workspace", str(tmp_path / "art"), "--json"]
    assert main(["init", *art]) == 0
    (tmp_path / "art" / "assets" / "sprites").mkdir(parents=True)
    (tmp_path / "art" / "assets" / "sprites" / "category.toml").write_text(
        "colors = 16\n[canvas]\nwidth = 64\nheight = 64\n"
    )
    assert main(["add", "sprites/knight", "--from", str(tmp_path / "knight.png"), *art]) == 0
    capsys.readouterr()
    assert main(["normalize", "sprites/knight", *art]) == 0
    env = json.loads(capsys.readouterr().out)
    out = read_png(Path(env["outputs"][0]))
    rgba = out.to_rgba()
    assert rgba.shape[:2] == (64, 64)
    opaque = rgba[..., 3] >= 128
    assert not opaque[0].any() and not opaque[:, 0].any()  # transparent background
    rows = np.nonzero(opaque.any(axis=1))[0]
    assert rows.max() - rows.min() + 1 >= 0.85 * 64  # the figure fills the canvas
    colours = rgba[opaque][:, :3].astype(int)
    assert (np.abs(colours - MAGENTA).sum(axis=1) > 60).all()  # no background colour
    assert (colours.sum(axis=1) < 120).sum() >= 40  # the dark outline survives
    assert ((colours[:, 0] > 140) & (colours[:, 1] < 80)).any()  # so does the red cape
