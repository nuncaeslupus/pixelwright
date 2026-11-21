"""`measure` and `recolor`: the numbers a style is judged by, and a material's new ramp."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from pixelwright.cli import main
from pixelwright.core.color import srgb8_to_oklab
from pixelwright.core.image import RGBImage
from pixelwright.core.look import mask_from, measure, recolor
from pixelwright.core.ramps import ramp
from pixelwright.io.png import read_png, write_png


def gradient(width: int = 16, levels: int = 16) -> np.ndarray:
    """A horizontal grey ramp of `levels` bands, opaque."""
    v = (np.arange(width) * levels // width * (255 // (levels - 1))).astype(np.uint8)
    img = np.zeros((4, width, 4), np.uint8)
    img[..., 0] = img[..., 1] = img[..., 2] = v
    img[..., 3] = 255
    return img


def test_more_bands_mean_more_colours_and_smaller_steps() -> None:
    coarse, fine = measure(gradient(16, 4)), measure(gradient(16, 16))
    assert (coarse["colors"], fine["colors"]) == (4, 16)
    assert fine["step_median"] < coarse["step_median"]


def test_isolated_pixels_are_counted() -> None:
    img = gradient(8, 2)
    img[..., :3] = 100
    img[1, 1, :3] = 200  # one lone pixel among 32
    assert measure(img)["isolated"] == pytest.approx(1 / 32, abs=1e-4)


def test_transparent_pixels_are_ignored_and_an_empty_image_refused() -> None:
    img = gradient()
    img[:, :8, 3] = 0
    assert measure(img)["pixels"] == 32
    img[..., 3] = 0
    with pytest.raises(ValueError):
        measure(img)


def test_recolor_keeps_the_order_of_light_inside_the_mask_only() -> None:
    img = gradient(16, 16)
    mask = np.zeros(img.shape[:2], bool)
    mask[:, :12] = True
    shades = ramp("8a5a3a", 7)
    out = recolor(img, mask, shades)
    light = srgb8_to_oklab(out[0, :12, :3])[:, 0]
    assert np.all(np.diff(light) >= -1e-9)  # still dark to light
    assert {tuple(c) for c in out[0, :12, :3]} <= set(shades)
    assert np.array_equal(out[:, 12:], img[:, 12:])  # outside the mask untouched


def test_light_moves_the_material_towards_the_light_end() -> None:
    img, mask = gradient(), np.ones((4, 16), bool)
    shades = ramp("8a5a3a", 7)
    base = srgb8_to_oklab(recolor(img, mask, shades)[..., :3])[..., 0].mean()
    lighter = srgb8_to_oklab(recolor(img, mask, shades, 0.3)[..., :3])[..., 0].mean()
    assert lighter > base


def test_mask_from_a_material_map_colour() -> None:
    m = np.zeros((2, 2, 4), np.uint8)
    m[..., 3] = 255
    m[0, 0, :3] = (10, 200, 10)
    m[1, 1, :3] = (200, 10, 10)
    assert mask_from(m, (10, 200, 10)).sum() == 1
    assert mask_from(m).sum() == 2


def test_cli_measure_and_recolor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    img, mask = tmp_path / "a.png", tmp_path / "m.png"
    write_png(img, RGBImage(gradient()))
    m = np.zeros((4, 16, 4), np.uint8)
    m[:, :8] = (255, 255, 255, 255)
    write_png(mask, RGBImage(m))
    assert main(["measure", str(img), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["colors"] == 16
    argv = ["recolor", str(img), "--mask", str(mask), "--key", "8a5a3a", "--json"]
    assert main(argv) == 0
    env = json.loads(capsys.readouterr().out)
    out = read_png(Path(env["outputs"][0]))
    assert isinstance(out, RGBImage) and env["data"]["changed"] > 0
    assert np.array_equal(out.rgba[:, 8:], gradient()[:, 8:])
