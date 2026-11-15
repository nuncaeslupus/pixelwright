"""OKLab / OKLCH conversions and perceptual color distance.

Reference: Björn Ottosson, "A perceptual color space for image processing" (2020).
All functions are vectorized: the last axis holds the three channels.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]

# Linear sRGB -> LMS (Ottosson).
_SRGB_TO_LMS = np.array(
    [
        [0.4122214708, 0.5363325363, 0.0514459929],
        [0.2119034982, 0.6806995451, 0.1073969566],
        [0.0883024619, 0.2817188376, 0.6299787005],
    ]
)
# CIE XYZ (D65) -> LMS (Ottosson's M1).
_XYZ_TO_LMS = np.array(
    [
        [0.8189330101, 0.3618667424, -0.1288597137],
        [0.0329845436, 0.9293118715, 0.0361456387],
        [0.0482003018, 0.2643662691, 0.6338517070],
    ]
)
# Nonlinear LMS -> OKLab (Ottosson's M2).
_LMS_TO_LAB = np.array(
    [
        [0.2104542553, 0.7936177850, -0.0040720468],
        [1.9779984951, -2.4285922050, 0.4505937099],
        [0.0259040371, 0.7827717662, -0.8086757660],
    ]
)
_LMS_TO_SRGB = np.linalg.inv(_SRGB_TO_LMS)
_LAB_TO_LMS = np.linalg.inv(_LMS_TO_LAB)


def _as_float(values: npt.ArrayLike) -> FloatArray:
    arr = np.asarray(values, dtype=np.float64)
    if arr.shape[-1:] != (3,):
        raise ValueError(f"last axis must have 3 channels, got shape {arr.shape}")
    return arr


def srgb_to_linear(srgb: npt.ArrayLike) -> FloatArray:
    """Gamma-encoded sRGB in [0, 1] to linear light."""
    c = _as_float(srgb)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(linear: npt.ArrayLike) -> FloatArray:
    """Linear light to gamma-encoded sRGB in [0, 1] (not clipped)."""
    c = _as_float(linear)
    a = np.abs(c)
    encoded = np.where(a <= 0.0031308, 12.92 * a, 1.055 * a ** (1 / 2.4) - 0.055)
    return np.sign(c) * encoded


def _lms_to_oklab(lms: FloatArray) -> FloatArray:
    lab: FloatArray = np.cbrt(lms) @ _LMS_TO_LAB.T
    return lab


def xyz_to_oklab(xyz: npt.ArrayLike) -> FloatArray:
    """CIE XYZ (D65, Y of white = 1) to OKLab."""
    return _lms_to_oklab(_as_float(xyz) @ _XYZ_TO_LMS.T)


def srgb_to_oklab(srgb: npt.ArrayLike) -> FloatArray:
    """Gamma-encoded sRGB in [0, 1] to OKLab."""
    return _lms_to_oklab(srgb_to_linear(srgb) @ _SRGB_TO_LMS.T)


def oklab_to_srgb(lab: npt.ArrayLike) -> FloatArray:
    """OKLab to gamma-encoded sRGB in [0, 1] (not clipped; out-of-gamut values fall outside)."""
    lms = (_as_float(lab) @ _LAB_TO_LMS.T) ** 3
    return linear_to_srgb(lms @ _LMS_TO_SRGB.T)


def srgb8_to_oklab(rgb8: npt.ArrayLike) -> FloatArray:
    """8-bit sRGB (0-255) to OKLab."""
    return srgb_to_oklab(np.asarray(rgb8, dtype=np.float64) / 255.0)


def oklab_to_srgb8(lab: npt.ArrayLike) -> npt.NDArray[np.uint8]:
    """OKLab to 8-bit sRGB, rounded and clipped to the gamut."""
    srgb = np.clip(oklab_to_srgb(lab), 0.0, 1.0)
    return np.rint(srgb * 255.0).astype(np.uint8)


def oklab_to_oklch(lab: npt.ArrayLike) -> FloatArray:
    """OKLab to OKLCH; hue in degrees [0, 360)."""
    arr = _as_float(lab)
    chroma = np.hypot(arr[..., 1], arr[..., 2])
    hue = np.degrees(np.arctan2(arr[..., 2], arr[..., 1])) % 360.0
    return np.stack([arr[..., 0], chroma, hue], axis=-1)


def oklch_to_oklab(lch: npt.ArrayLike) -> FloatArray:
    """OKLCH (hue in degrees) to OKLab."""
    arr = _as_float(lch)
    h = np.radians(arr[..., 2])
    return np.stack([arr[..., 0], arr[..., 1] * np.cos(h), arr[..., 1] * np.sin(h)], axis=-1)


def delta_e(lab1: npt.ArrayLike, lab2: npt.ArrayLike) -> FloatArray:
    """Euclidean distance in OKLab (deltaE_ok), broadcast over leading axes."""
    diff = _as_float(lab1) - _as_float(lab2)
    return np.sqrt(np.sum(diff * diff, axis=-1))
