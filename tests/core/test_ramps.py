"""Hue-shifted ramps: darker towards blue-violet, lighter towards yellow."""

from __future__ import annotations

import numpy as np
import pytest

from pixelwright.core.color import oklab_to_oklch, srgb8_to_oklab
from pixelwright.core.ramps import ADVENTURE, ramp, ramp_palette


def lch(rgb: tuple[int, int, int]) -> np.ndarray:
    return oklab_to_oklch(srgb8_to_oklab(np.array(rgb, np.uint8)))


def test_ramp_runs_dark_to_light_with_the_key_in_the_middle() -> None:
    shades = ramp("8a5a3a", 5)
    lights = [lch(c)[0] for c in shades]
    assert lights == sorted(lights)
    assert shades[2] == (0x8A, 0x5A, 0x3A)


def test_hue_turns_cool_in_shadow_and_warm_in_light() -> None:
    shades = ramp("5a8a3a", 5)  # green, hue ~ 135
    key, dark, light = lch(shades[2])[2], lch(shades[0])[2], lch(shades[-1])[2]
    assert dark > key + 10  # towards 285 (blue-violet)
    assert light < key - 10  # towards 95 (yellow)


def test_palette_has_a_row_per_ramp_and_shared_ends() -> None:
    palette = ramp_palette(ADVENTURE, 5)
    assert palette.columns == 5
    names = [c.name for c in palette.colors]
    assert names[:2] == ["skin-light-1", "skin-light-2"] and names[-2:] == ["ink", "paper"]
    assert len(palette) <= 5 * len(ADVENTURE) + 2


def test_bad_key_is_refused() -> None:
    with pytest.raises(ValueError):
        ramp("abc")


def test_hue_families_join_a_materials_darks_and_lights() -> None:
    from pixelwright.core.ramps import hue_families

    greens = [(30, 60, 20), (60, 110, 40), (120, 180, 90)]  # one material, three shades
    reds = [(90, 20, 25), (170, 50, 60)]
    rgb = np.array(greens * 20 + reds * 20, np.uint8)
    keys = hue_families(srgb8_to_oklab(rgb), np.ones(len(rgb)), 2)
    hues = sorted(lch(tuple(int(k[i : i + 2], 16) for i in (0, 2, 4)))[2] for k in keys.values())
    assert len(keys) == 2 and hues[0] < 40 and 110 < hues[1] < 160  # a red and a green
