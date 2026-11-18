"""A scene set's palette: each scene keeps its own colours, lights included."""

from __future__ import annotations

import numpy as np

from pixelwright.core.color import srgb8_to_oklab
from pixelwright.core.image import RGBImage
from pixelwright.flow import palette_per_image


def _scene(colors: list[tuple[int, int, int]], size: tuple[int, int]) -> RGBImage:
    rng = np.random.default_rng(len(colors))
    idx = rng.integers(0, len(colors), size)
    return RGBImage.from_array(np.array(colors, np.uint8)[idx])


def _has(palette_colors: list[tuple[int, int, int]], target: tuple[int, int, int]) -> bool:
    lab = srgb8_to_oklab(np.array(palette_colors, np.uint8))
    t = srgb8_to_oklab(np.array([target], np.uint8))[0]
    return bool(np.min(np.linalg.norm(lab - t, axis=1)) < 0.03)


def test_a_small_scene_keeps_its_lights_beside_a_big_one() -> None:
    greens = [(20 + 9 * i, 90 + 8 * i, 30 + 3 * i) for i in range(16)]
    grass = _scene(greens, (180, 320))
    fire = [(30, 25, 40), (60, 50, 70), (200, 90, 20), (250, 170, 60), (255, 250, 230)]
    crypt = _scene(fire, (40, 60))
    shared = [(c.r, c.g, c.b) for c in palette_per_image([grass, crypt], 6).colors]
    assert _has(shared, (255, 250, 230)) and _has(shared, (200, 90, 20))
    assert sum(_has(shared, g) for g in greens) >= 6  # the big scene keeps its own share
    assert len(shared) == len(set(shared))
