import numpy as np
import pytest

from pixelwright.core.image import IndexedImage, RGBImage
from pixelwright.core.palette import Color, Palette

PALETTE = Palette([Color(0, 0, 0), Color(255, 0, 0)])


def test_indexed_to_rgba_uses_palette_and_alpha() -> None:
    image = IndexedImage.from_array([[0, 1]], PALETTE, alpha=[[True, False]])
    np.testing.assert_array_equal(image.to_rgba(), [[[0, 0, 0, 255], [255, 0, 0, 0]]])
    assert (image.width, image.height) == (2, 1)


def test_indexed_rejects_out_of_palette_and_bad_alpha() -> None:
    with pytest.raises(ValueError, match="outside"):
        IndexedImage.from_array([[2]], PALETTE)
    with pytest.raises(ValueError, match="alpha"):
        IndexedImage.from_array([[0, 1]], PALETTE, alpha=[[True]])


def test_rgb_image_from_rgb_is_opaque() -> None:
    image = RGBImage.from_array(np.zeros((2, 3, 3), dtype=np.uint8))
    assert image.rgba.shape == (2, 3, 4)
    assert (image.rgba[..., 3] == 255).all()
    with pytest.raises(ValueError):
        RGBImage(np.zeros((2, 2), dtype=np.uint8))
