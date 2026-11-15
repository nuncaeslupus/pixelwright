import numpy as np
import pytest

from pixelwright.core import color

TOL = 1e-3

# Ottosson's published XYZ (D65) -> OKLab table.
OTTOSSON_XYZ = [
    ((0.950, 1.000, 1.089), (1.000, 0.000, 0.000)),
    ((1.000, 0.000, 0.000), (0.450, 1.236, -0.019)),
    ((0.000, 1.000, 0.000), (0.922, -0.671, 0.263)),
    ((0.000, 0.000, 1.000), (0.153, -1.415, -0.449)),
]
# sRGB primaries, from Ottosson's sRGB matrices (also CSS Color 4 reference values).
SRGB_REFERENCE = [
    ((1.0, 1.0, 1.0), (1.0, 0.0, 0.0)),
    ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
    ((1.0, 0.0, 0.0), (0.62796, 0.22486, 0.12585)),
    ((0.0, 1.0, 0.0), (0.86644, -0.23389, 0.17950)),
    ((0.0, 0.0, 1.0), (0.45201, -0.03246, -0.31153)),
]


def test_oklab_reference_values_match_published() -> None:
    xyz, expected = zip(*OTTOSSON_XYZ, strict=True)
    err_xyz = np.abs(color.xyz_to_oklab(xyz) - np.array(expected)).max()
    rgb, expected_rgb = zip(*SRGB_REFERENCE, strict=True)
    err_rgb = np.abs(color.srgb_to_oklab(rgb) - np.array(expected_rgb)).max()
    assert max(err_xyz, err_rgb) <= TOL


def test_srgb8_roundtrip_is_exact() -> None:
    rng = np.random.default_rng(0)
    rgb8 = rng.integers(0, 256, size=(1000, 3), dtype=np.uint8)
    back = color.oklab_to_srgb8(color.srgb8_to_oklab(rgb8))
    assert np.array_equal(back, rgb8)


def test_oklch_roundtrip_and_hue_range() -> None:
    lab = color.srgb_to_oklab(np.random.default_rng(1).random((200, 3)))
    lch = color.oklab_to_oklch(lab)
    assert ((lch[..., 2] >= 0) & (lch[..., 2] < 360)).all()
    np.testing.assert_allclose(color.oklch_to_oklab(lch), lab, atol=1e-12)


def test_delta_e_is_symmetric_and_zero_on_identity() -> None:
    a = color.srgb_to_oklab([[1.0, 0.0, 0.0], [0.2, 0.4, 0.6]])
    b = color.srgb_to_oklab([[0.0, 0.0, 1.0], [0.2, 0.4, 0.6]])
    d = color.delta_e(a, b)
    assert d[1] == 0.0
    assert d[0] > 0.3
    np.testing.assert_array_equal(d, color.delta_e(b, a))


def test_rejects_wrong_channel_count() -> None:
    with pytest.raises(ValueError, match="3 channels"):
        color.srgb_to_oklab([0.1, 0.2])
