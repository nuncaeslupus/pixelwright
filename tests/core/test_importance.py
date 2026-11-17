"""Local colour importance: small colours that stand out keep their palette entries."""

from __future__ import annotations

import numpy as np

from pixelwright.core.color import srgb8_to_oklab
from pixelwright.core.image import RGBImage
from pixelwright.core.importance import analyze_colors, importance_map
from pixelwright.core.quantize import discover_palette

GLOW = (255, 200, 40)


def _night_with_a_window() -> RGBImage:
    """A dark two-tone 120x80 scene (sky gradient over ground) with one lit 3x3 window."""
    rgb = np.zeros((80, 120, 3), np.uint8)
    for y in range(80):  # a dusk sky from deep blue to pink, then darker ground
        rgb[y] = (10 + 4 * y, 10 + 2 * y, 60 + 2 * y) if y < 50 else (30 + y - 50, 50, 25)
    rgb[55:58, 70:73] = GLOW
    return RGBImage(np.dstack([rgb, np.full((80, 120), 255, np.uint8)]))


def _distance_to(palette_rgb: list[tuple[int, int, int]], color: tuple[int, int, int]) -> float:
    lab = srgb8_to_oklab(np.array(palette_rgb, np.uint8))
    return float(np.sqrt(((lab - srgb8_to_oklab(np.array(color, np.uint8))) ** 2).sum(1)).min())


def test_the_window_is_the_most_important_spot() -> None:
    imp = importance_map(_night_with_a_window())
    assert imp[56, 71] == 1.0
    assert float(np.median(imp)) < 0.1


def test_the_window_is_reported_as_an_accent() -> None:
    accents = [g for g in analyze_colors(_night_with_a_window()) if g.accent]
    assert len(accents) == 1 and accents[0].share < 0.002
    assert _distance_to([accents[0].color], GLOW) < 0.02


def test_importance_keeps_the_window_colour_in_a_small_palette() -> None:
    image = _night_with_a_window()
    plain = [(c.r, c.g, c.b) for c in discover_palette(image, 4).colors]
    kept = [
        (c.r, c.g, c.b) for c in discover_palette(image, 4, importance=importance_map(image)).colors
    ]
    assert _distance_to(plain, GLOW) > 0.1
    assert _distance_to(kept, GLOW) < 0.03
