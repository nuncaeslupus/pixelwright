from pathlib import Path

import numpy as np
import pytest

from pixelwright.core.image import IndexedImage, RGBImage
from pixelwright.core.palette import Color, Palette
from pixelwright.io.png import read_png, write_png

PALETTE = Palette([Color(10, 20, 30), Color(200, 100, 50), Color(0, 0, 0), Color(255, 255, 255)])


def _indexed(alpha: bool) -> IndexedImage:
    rng = np.random.default_rng(5)
    idx = rng.integers(0, len(PALETTE), size=(6, 8))
    mask = rng.random((6, 8)) > 0.3 if alpha else None
    return IndexedImage.from_array(idx, PALETTE, alpha=mask)


@pytest.mark.parametrize("alpha", [False, True])
def test_indexed_png_roundtrip(tmp_path: Path, alpha: bool) -> None:
    image = _indexed(alpha)
    path = tmp_path / "image.png"
    write_png(path, image)
    back = read_png(path)
    assert isinstance(back, IndexedImage)
    assert back.palette.rgb_array().tolist() == PALETTE.rgb_array().tolist()
    opaque = image.opaque()
    np.testing.assert_array_equal(back.opaque(), opaque)
    np.testing.assert_array_equal(back.indices[opaque], image.indices[opaque])


def test_rgba_png_roundtrip(tmp_path: Path) -> None:
    rgba = np.random.default_rng(6).integers(0, 256, size=(5, 4, 4), dtype=np.uint8)
    path = tmp_path / "gen.png"
    write_png(path, RGBImage(rgba))
    back = read_png(path)
    assert isinstance(back, RGBImage)
    np.testing.assert_array_equal(back.rgba, rgba)


def test_indexed_png_palette_limit(tmp_path: Path) -> None:
    big = Palette([Color(i % 256, i // 256, 0) for i in range(257)])
    with pytest.raises(ValueError, match="256"):
        write_png(tmp_path / "x.png", IndexedImage.from_array([[0]], big))
