import numpy as np
import pytest

from pixelwright.core.palette import Color, Palette, Ramp, analyze_ramp


def test_palette_arrays_and_lookup() -> None:
    palette = Palette([Color(0, 0, 0), Color(255, 255, 255)])
    assert palette.rgb_array().shape == (2, 3)
    np.testing.assert_allclose(palette.oklab()[1], [1.0, 0.0, 0.0], atol=1e-6)
    assert palette.index_of((255, 255, 255)) == 1
    with pytest.raises(KeyError):
        palette.index_of(Color(1, 2, 3))


def test_ramp_validation() -> None:
    with pytest.raises(ValueError, match="two"):
        Ramp((1,))
    with pytest.raises(ValueError, match="repeats"):
        Ramp((1, 2, 1))


def test_analyze_ramp_reports_lightness_and_hue_shift() -> None:
    # Dark blue-purple to light yellow-ish: lightness rises, hue shifts.
    palette = Palette([Color(30, 20, 60), Color(90, 70, 110), Color(200, 180, 120)])
    report = analyze_ramp(palette, Ramp((0, 1, 2)))
    assert report.monotonic_lightness
    assert abs(report.hue_shift_deg) > 30
    assert not analyze_ramp(palette, (2, 0)).monotonic_lightness
