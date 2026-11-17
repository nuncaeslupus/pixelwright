"""Local colour importance: small colours that stand out keep their palette entries."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage

from pixelwright.cli import main
from pixelwright.core.color import srgb8_to_oklab
from pixelwright.core.image import RGBImage
from pixelwright.core.importance import analyze_colors, importance_map
from pixelwright.core.quantize import discover_palette
from pixelwright.io.png import write_png

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


def test_near_black_noise_is_one_palette_colour_and_outlines_survive() -> None:
    """JPEG noise in a large dark area must not split black into several entries: a 1-px
    outline would then look like orphan pixels and `clean` would erase it."""
    from pixelwright.core.clean import clean
    from pixelwright.core.quantize import quantize_fixed

    rng = np.random.default_rng(3)
    rgb = np.full((60, 80, 3), (18, 20, 42), np.int16)  # navy wall
    rgb[30, 5:75] = (0, 0, 0)  # a 1-px outline
    rgb[5:25, 10:30] = (120, 60, 110)  # a purple counter
    rgb += rng.integers(-3, 4, rgb.shape).astype(np.int16)
    rgb = np.clip(rgb, 0, 255)
    image = RGBImage(np.dstack([rgb.astype(np.uint8), np.full((60, 80), 255, np.uint8)]))
    palette = discover_palette(image, 8)
    blacks = [c for c in palette.colors if c.r + c.g + c.b < 20]
    assert len(blacks) == 1
    cleaned, _ = clean(quantize_fixed(image, palette)[0])
    line = cleaned.indices[30, 5:75]
    assert (line == line[0]).all()


def test_normalize_keeps_a_lone_star(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A single bright pixel in a dark sky is meant (a star), not an orphan to clean."""
    sky = np.zeros((18, 32, 4), np.uint8)
    sky[..., :3], sky[..., 3] = (20, 22, 50), 255
    ground = np.random.default_rng(4).integers(0, 2, (9, 32)).astype(bool)
    sky[9:, :, :3] = np.where(ground[..., None], (40, 30, 60), (70, 50, 40))  # rough ground
    sky[4, 10, :3] = (255, 250, 220)
    big = np.repeat(np.repeat(sky, 4, 0), 4, 1)
    write_png(tmp_path / "sky.png", RGBImage(big))
    art = ["--workspace", str(tmp_path / "art"), "--json"]
    assert main(["init", *art]) == 0
    assert main(["add", "scenes/sky", "--from", str(tmp_path / "sky.png"), *art]) == 0
    assert main(["normalize", "scenes/sky", *art]) == 0
    capsys.readouterr()
    version = tmp_path / "art" / "assets" / "scenes" / "sky" / "versions" / "v001.png"
    pixels = np.asarray(PILImage.open(version).convert("RGB"))
    assert pixels[4, 10].sum() > 600


def test_a_twinkle_keeps_one_glow_colour() -> None:
    """A lone star with four arms in slightly different JPEG shades: the arms are kept
    and take one palette colour; a faint speck next to a plain star is not protected."""
    from pixelwright.core.palette import Color, Palette
    from pixelwright.core.quantize import quantize_fixed
    from pixelwright.flow import _glow

    rgb = np.zeros((20, 20, 3), np.uint8)
    rgb[:] = (30, 25, 60)
    rgb[5, 5] = (250, 225, 180)
    for (y, x), c in zip(((4, 5), (6, 5), (5, 4), (5, 6)), (140, 150, 156, 162), strict=True):
        rgb[y, x] = (c, c - 25, c - 20)
    rgb[14, 14] = (250, 225, 180)  # a plain star with a faint JPEG speck beside it
    rgb[14, 15] = (40, 33, 66)
    image = RGBImage(np.dstack([rgb, np.full((20, 20), 255, np.uint8)]))
    pal = Palette([Color(30, 25, 60), Color(250, 225, 180), Color(130, 110, 120),
                   Color(160, 140, 130), Color(42, 34, 68)])  # fmt: skip
    indexed, _ = quantize_fixed(image, pal)
    out, protect = _glow(indexed, image, importance_map(image), pal)
    arms = {int(out.indices[p]) for p in ((4, 5), (6, 5), (5, 4), (5, 6))}
    assert len(arms) == 1 and arms != {0}
    assert protect[5, 5] and protect[4, 5] and not protect[14, 15]
