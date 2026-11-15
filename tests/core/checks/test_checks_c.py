import numpy as np

from pixelwright.core.checks import (
    check_aa,
    check_depth_falloff,
    check_diagnostics,
    check_dither_zones,
    check_figure_ground,
    check_outline_share,
    check_ramps,
    check_selout,
)
from pixelwright.core.color import oklab_to_srgb8, oklch_to_oklab
from pixelwright.core.image import IndexedImage
from pixelwright.core.palette import Color, Palette, Ramp, Ramps

PAL = Palette(
    [
        Color(0, 0, 0),
        Color(240, 240, 240),
        Color(120, 120, 120),
        Color(60, 30, 90),
        Color(200, 120, 60),
    ]
)


def test_ramps_flags_flat_and_unshifted_ramps() -> None:
    lch = [[0.3 + 0.15 * i, 0.08, 300.0 + 20.0 * i] for i in range(4)]  # 20 deg hue steps
    rgb = oklab_to_srgb8(oklch_to_oklab(lch))
    good = Palette([Color(int(c[0]), int(c[1]), int(c[2])) for c in rgb])
    assert check_ramps(good, Ramps({"warm": Ramp((0, 1, 2, 3))})).status == "pass"
    bad = Palette([Color(100, 0, 0), Color(102, 0, 0), Color(200, 0, 0)])
    result = check_ramps(bad, Ramps({"red": Ramp((0, 1, 2)), "down": Ramp((2, 0))}))
    assert result.status == "warn" and set(result.details["problems"]) == {"red", "down"}


def _checker(h: int = 16, w: int = 16) -> IndexedImage:
    yy, xx = np.indices((h, w))
    return IndexedImage(((yy + xx) % 2).astype(np.uint16), PAL)


def test_dither_zones_respects_declared_zones() -> None:
    assert check_dither_zones(_checker()).status == "warn"
    zones = np.ones((16, 16), dtype=bool)
    result = check_dither_zones(_checker(), zones)
    assert result.status == "pass" and result.details["inside_zones"] > 0
    flat = IndexedImage(np.zeros((8, 8), dtype=np.uint16), PAL)
    assert check_dither_zones(flat).status == "pass"


def _sprite(aa: bool) -> IndexedImage:
    idx = np.full((12, 12), 1, dtype=np.uint16)  # light fill
    alpha = np.zeros((12, 12), dtype=bool)
    alpha[2:10, 2:10] = True
    idx[2, 2:10] = idx[9, 2:10] = idx[2:10, 2] = idx[2:10, 9] = 0  # black outline
    if aa:
        idx[2, 5] = 2  # mid gray on the edge
    return IndexedImage(idx, PAL, alpha)


def test_aa_on_alpha_boundary() -> None:
    assert check_aa(_sprite(False)).status == "pass"
    assert check_aa(_sprite(True)).value == 1.0


def test_selout_reports_black_share() -> None:
    result = check_selout(_sprite(False))
    assert result.details["pure_black_share"] == 1.0 and result.details["delta_l"] > 0.5


def test_outline_share_counts_dark_strokes() -> None:
    idx = np.ones((20, 20), dtype=np.uint16)
    idx[5, 2:18] = 0
    result = check_outline_share(IndexedImage(idx, PAL))
    assert result.details["pixels"] == 16


def test_depth_falloff_monotonic() -> None:
    rng = np.random.default_rng(0)
    idx = np.zeros((30, 30), dtype=np.uint16)
    near, mid, far = np.zeros((3, 30, 30), dtype=bool)
    near[20:], mid[10:20], far[:10] = True, True, True
    idx[20:] = rng.choice([0, 1], (10, 30))  # high contrast near
    idx[10:20] = rng.choice([2, 1], (10, 30))
    idx[:10] = 1  # flat sky
    image = IndexedImage(idx, PAL)
    assert check_depth_falloff(image, [near, mid, far]).status == "pass"
    assert check_depth_falloff(image, [far, mid, near]).status == "warn"


def test_figure_ground_delta() -> None:
    idx = np.ones((20, 20), dtype=np.uint16)
    sprite = np.zeros((20, 20), dtype=bool)
    sprite[5:15, 5:15] = True
    idx[sprite] = 0
    assert check_figure_ground(IndexedImage(idx, PAL), sprite).status == "pass"
    idx[sprite] = 1
    assert check_figure_ground(IndexedImage(idx, PAL), sprite).status == "warn"


def test_diagnostics_reports_peak_and_slope() -> None:
    idx = np.ones((32, 32), dtype=np.uint16)
    idx[14:18, 14:18] = 0
    focal = np.zeros((32, 32), dtype=bool)
    focal[10:22, 10:22] = True
    result = check_diagnostics(IndexedImage(idx, PAL), focal)
    assert result.details["peak_in_focal"] is True
    assert result.status == "pass"
