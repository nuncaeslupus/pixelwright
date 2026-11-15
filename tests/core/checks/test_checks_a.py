from pathlib import Path

import numpy as np

from pixelwright.core import render
from pixelwright.core.checks import (
    check_focal_contrast,
    check_grid,
    check_palette,
    check_value_groups,
    read_report,
    write_report,
)
from pixelwright.core.image import IndexedImage, RGBImage
from pixelwright.core.palette import Color, Palette

PAL = Palette([Color(0, 0, 0), Color(128, 128, 128), Color(255, 255, 255)])


def _image() -> IndexedImage:
    idx = np.zeros((32, 32), dtype=np.uint16)
    idx[8:24, 8:24] = 2
    idx[12:20, 12:20] = 1
    return IndexedImage(idx, PAL)


def test_palette_check_passes_in_palette_and_fails_off_palette() -> None:
    assert check_palette(_image(), PAL).status == "pass"
    rgba = _image().to_rgba()
    rgba[3, 5, :3] = (1, 2, 3)
    result = check_palette(RGBImage(rgba), PAL)
    assert result.status == "fail" and result.details["off_palette_pixels"] == 1
    assert result.regions == ((0, 0, 16, 16),)
    assert check_palette(_image(), PAL, budget=2).status == "warn"


def test_grid_check() -> None:
    big = RGBImage(render.upscale(_image(), 4))
    assert check_grid(big, 4).status == "pass"
    rgba = big.rgba.copy()
    rgba[5, 6] = (9, 9, 9, 255)
    result = check_grid(RGBImage(rgba), 4)
    assert result.status == "fail" and result.regions == ((1, 1, 1, 1),)


def test_value_groups_counts_lightness_bands() -> None:
    assert check_value_groups(_image()).value == 3.0
    ramp = np.repeat(np.arange(0, 256, 32, dtype=np.uint16)[None], 4, axis=0) // 32
    many = Palette([Color(v, v, v) for v in range(0, 256, 32)])
    result = check_value_groups(IndexedImage(ramp.astype(np.uint16), many), max_groups=5)
    assert result.value >= 6 and result.status == "warn"


def test_focal_contrast_inside_vs_outside() -> None:
    image = _image()
    focal = np.zeros((32, 32), dtype=bool)
    focal[8:24, 8:24] = True
    assert check_focal_contrast(image, focal).status == "pass"
    elsewhere = np.zeros((32, 32), dtype=bool)
    elsewhere[24:, 24:] = True
    result = check_focal_contrast(image, elsewhere)
    assert result.status == "warn" and result.regions


def test_report_roundtrip(tmp_path: Path) -> None:
    results = [check_palette(_image(), PAL), check_value_groups(_image())]
    write_report(tmp_path / "report.json", results)
    back = read_report(tmp_path / "report.json")
    assert [r["check"] for r in back] == ["palette", "value-groups"]
    assert back[0]["status"] == "pass"
