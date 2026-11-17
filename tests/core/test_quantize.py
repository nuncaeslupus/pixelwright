import numpy as np
import pytest

from pixelwright.core.image import RGBImage
from pixelwright.core.palette import Color, Palette
from pixelwright.core.quantize import bayer_matrix, discover_palette, quantize_fixed

PALETTE = Palette(
    [
        Color(0, 0, 0),
        Color(255, 255, 255),
        Color(200, 40, 40),
        Color(40, 90, 200),
        Color(90, 160, 60),
    ]
)


def _noise(h: int = 40, w: int = 50, seed: int = 0) -> RGBImage:
    return RGBImage.from_array(np.random.default_rng(seed).integers(0, 256, (h, w, 3)))


def test_quantize_fixed_palette_output_fully_in_palette() -> None:
    image = _noise()
    out, report = quantize_fixed(image, PALETTE)
    in_palette = np.isin(out.indices, np.arange(len(PALETTE)))
    compliance = float(in_palette.mean())
    assert compliance == 1.0
    rgba = out.to_rgba()[..., :3].reshape(-1, 3)
    allowed = {c.rgb for c in PALETTE}
    assert {tuple(int(v) for v in px) for px in rgba} <= allowed
    assert report.dithered_pixels == 0
    assert 0 < report.mean_error <= report.max_error


def test_exact_palette_colors_map_to_themselves() -> None:
    rgb = PALETTE.rgb_array()[np.array([[0, 1, 2, 3, 4]])]
    out, report = quantize_fixed(RGBImage.from_array(rgb), PALETTE)
    np.testing.assert_array_equal(out.indices, [[0, 1, 2, 3, 4]])
    assert report.max_error == pytest.approx(0.0, abs=1e-9)


def test_dithering_only_inside_mask() -> None:
    gray = np.full((8, 8, 3), 128, dtype=np.uint8)  # between black and white
    bw = Palette([Color(0, 0, 0), Color(255, 255, 255)])
    mask = np.zeros((8, 8), dtype=bool)
    mask[:, 4:] = True
    out, report = quantize_fixed(RGBImage.from_array(gray), bw, dither_mask=mask)
    assert len(np.unique(out.indices[:, :4])) == 1  # flat outside the mask
    assert set(np.unique(out.indices[:, 4:])) == {0, 1}  # mixed inside
    assert report.dithered_pixels > 0


def test_transparent_pixels_become_alpha() -> None:
    rgba = np.zeros((2, 2, 4), dtype=np.uint8)
    rgba[0, 0] = [255, 255, 255, 255]
    out, _ = quantize_fixed(RGBImage(rgba), PALETTE)
    assert out.alpha is not None
    assert out.alpha.tolist() == [[True, False], [False, False]]


def test_bayer_matrix_is_a_permutation() -> None:
    m = bayer_matrix(4)
    assert sorted((m * 16 - 0.5).round().astype(int).ravel().tolist()) == list(range(16))
    with pytest.raises(ValueError):
        bayer_matrix(3)


@pytest.mark.parametrize("method", ["kmeans", "median-cut"])
def test_discover_recovers_planted_colors(method: str) -> None:
    rng = np.random.default_rng(1)
    target = Palette([Color(30, 20, 40), *PALETTE.colors[1:]])  # no clipped black
    planted = target.rgb_array()
    idx = rng.integers(0, len(planted), (30, 30))
    noisy = np.clip(planted[idx].astype(int) + rng.integers(-4, 5, (30, 30, 3)), 0, 255)
    found = discover_palette(RGBImage.from_array(noisy.astype(np.uint8)), 5, method=method)
    assert len(found) == 5
    lab_found, lab_true = found.oklab(), target.oklab()
    dist = np.sqrt(((lab_true[:, None] - lab_found[None]) ** 2).sum(axis=2)).min(axis=1)
    assert dist.max() < 0.03


def test_discover_is_deterministic_and_bounded() -> None:
    image = _noise(seed=2)
    a = discover_palette(image, 8)
    assert a == discover_palette(image, 8)
    assert len(a) <= 8


def test_large_palette_keeps_near_shades() -> None:
    """VGA shades 4 RGB steps apart are meant: a 64-colour request keeps them apart."""
    ramp = np.array([[(20 + 3 * i, 30 + 2 * i, 20) for i in range(64)]], np.uint8)
    found = discover_palette(RGBImage.from_array(np.repeat(ramp, 4, axis=0)), 64)
    assert len(found) >= 56


def test_white_keeps_a_neutral_entry() -> None:
    """A small palette must not turn a white border into the pale green next to it."""
    from pixelwright.core.importance import importance_map

    art = np.zeros((40, 40, 3), np.uint8)
    art[...] = (60, 140, 50)
    art[:20] = (180, 230, 160)
    art[0, :] = art[:, 0] = (255, 255, 255)
    image = RGBImage.from_array(art)
    found = discover_palette(image, 2, importance=importance_map(image))
    assert min(sum(abs(c - 255) for c in (col.r, col.g, col.b)) for col in found) < 12
