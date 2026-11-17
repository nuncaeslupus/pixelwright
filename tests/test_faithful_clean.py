"""Rich pixel art keeps its lone pixels: clean only removes quantising flecks."""

from __future__ import annotations

import numpy as np

from pixelwright import flow
from pixelwright.core.clean import clean
from pixelwright.core.color import srgb8_to_oklab
from pixelwright.core.image import RGBImage
from pixelwright.core.palette import Color, Palette
from pixelwright.core.quantize import quantize_fixed

STONE, CRACK, FLECK = (120, 110, 100), (40, 36, 34), (124, 113, 102)


def test_lone_detail_survives_but_flecks_go() -> None:
    rgb = np.zeros((9, 9, 3), np.uint8)
    rgb[:] = STONE
    rgb[2, 2] = CRACK  # a meant dark pixel
    rgb[6, 6] = FLECK  # a near-equal colour: quantising noise
    native = RGBImage(np.dstack([rgb, np.full((9, 9), 255, np.uint8)]))
    palette = Palette(tuple(Color(*c) for c in (STONE, CRACK, FLECK)))
    indexed, _ = quantize_fixed(native, palette)
    cleaned, _ = clean(indexed)
    assert tuple(cleaned.to_rgba()[2, 2, :3]) == STONE  # what clean alone does
    kept = flow._faithful(cleaned, indexed, native).to_rgba()
    assert tuple(kept[2, 2, :3]) == CRACK
    assert tuple(kept[6, 6, :3]) == STONE


def test_sprite_that_fits_keeps_its_pixels() -> None:
    fig = np.zeros((30, 20, 4), np.uint8)
    fig[..., :3] = np.random.default_rng(2).integers(0, 255, (30, 20, 3))
    fig[..., 3] = 255
    fits = flow._sprite(RGBImage(fig), (64, 64), (255, 0, 255))
    assert fits.image.rgba.shape[:2] == (64, 64)
    assert (fits.image.rgba[34:, 22:42] == fig).all()  # centred, feet at the bottom
    big = flow._sprite(RGBImage(fig), (16, 16), (255, 0, 255))
    assert big.image.rgba.shape[:2] == (16, 16) and "20x30" in big.warnings[0]


def test_shared_palette_gives_a_small_image_its_colours() -> None:
    ramp = np.linspace(40, 220, 120).astype(np.uint8)
    big = np.dstack([np.tile(ramp, (120, 1))] * 3 + [np.full((120, 120), 255, np.uint8)])
    small = np.full((20, 20, 4), 255, np.uint8)
    small[..., :3] = (180, 140, 60)
    palette = flow.palette_from([RGBImage(big), RGBImage(small)], 6)
    lab = srgb8_to_oklab(np.array([[c.r, c.g, c.b] for c in palette.colors], np.uint8))
    target = srgb8_to_oklab(np.array([(180, 140, 60)], np.uint8))[0]
    assert np.linalg.norm(lab - target, axis=1).min() < 0.03
