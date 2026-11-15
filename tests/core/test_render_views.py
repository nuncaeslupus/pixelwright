import numpy as np
import pytest

from pixelwright.core import render
from pixelwright.core.image import IndexedImage, RGBImage
from pixelwright.core.palette import Color, Palette

PALETTE = Palette([Color(0, 0, 0), Color(255, 255, 255), Color(255, 0, 0), Color(40, 80, 160)])


def _sample() -> IndexedImage:
    rng = np.random.default_rng(3)
    return IndexedImage.from_array(rng.integers(0, len(PALETTE), size=(7, 9)), PALETTE)


@pytest.mark.parametrize("factor", [1, 2, 3, 6, 12])
def test_upscale_integer_factor_is_blocky(factor: int) -> None:
    image = _sample()
    big = render.upscale(image, factor)
    assert big.shape == (7 * factor, 9 * factor, 4)
    blocks = big.reshape(7, factor, 9, factor, 4)
    mismatches = int((blocks != blocks[:, :1, :, :1, :]).any(axis=(1, 3, 4)).sum())
    assert mismatches == 0
    np.testing.assert_array_equal(blocks[:, 0, :, 0, :], image.to_rgba())


def test_upscale_rejects_non_integer_factor() -> None:
    with pytest.raises(ValueError):
        render.upscale(_sample(), 0)
    with pytest.raises(ValueError):
        render.upscale(_sample(), 1.5)  # type: ignore[arg-type]


def test_grayscale_golden() -> None:
    image = IndexedImage.from_array([[0, 1, 2]], PALETTE, alpha=[[True, True, False]])
    gray = render.grayscale(image)
    # OKLab L of black, white and sRGB red (0.62796) -> 0, 255, 160.
    np.testing.assert_array_equal(
        gray[0], [[0, 0, 0, 255], [255, 255, 255, 255], [160, 160, 160, 0]]
    )


def test_value_map_golden() -> None:
    image = IndexedImage.from_array([[0, 3, 2, 1]], PALETTE)
    values = render.value_map(image, levels=3)[0, :, 0]
    # L: 0.0, ~0.44, 0.63, 1.0 -> bands 0, 1, 1, 2 -> 0, 128, 128, 255.
    np.testing.assert_array_equal(values, [0, 128, 128, 255])


def test_overlay_only_touches_mask() -> None:
    image = RGBImage.from_array(np.zeros((2, 2, 3), dtype=np.uint8))
    mask = np.array([[True, False], [False, False]])
    out = render.overlay(image, mask, color=(200, 100, 0), opacity=0.5)
    np.testing.assert_array_equal(out[0, 0], [100, 50, 0, 255])
    np.testing.assert_array_equal(out[1:, :], image.rgba[1:, :])
    np.testing.assert_array_equal(out[0, 1], image.rgba[0, 1])
