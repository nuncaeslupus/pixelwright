"""Renders for review: integer upscale, grayscale, value map, mask overlay."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from pixelwright.core.color import srgb8_to_oklab
from pixelwright.core.image import U8, Image, Mask


def upscale(image: Image | U8, factor: int) -> U8:
    """Nearest-neighbour integer upscale: every pixel becomes a factor x factor block."""
    if not isinstance(factor, int) or factor < 1:
        raise ValueError(f"factor must be a positive integer, got {factor!r}")
    rgba = image if isinstance(image, np.ndarray) else image.to_rgba()
    return np.repeat(np.repeat(rgba, factor, axis=0), factor, axis=1)


def lightness(image: Image | U8) -> npt.NDArray[np.float64]:
    """OKLab L per pixel, in [0, 1]."""
    rgba = image if isinstance(image, np.ndarray) else image.to_rgba()
    return srgb8_to_oklab(rgba[..., :3])[..., 0]


def _gray(values: npt.NDArray[np.float64], alpha: U8) -> U8:
    g = np.rint(np.clip(values, 0.0, 1.0) * 255.0).astype(np.uint8)
    return np.stack([g, g, g, alpha], axis=-1)


def grayscale(image: Image | U8) -> U8:
    """Perceptual grayscale (OKLab L), alpha kept."""
    rgba = image if isinstance(image, np.ndarray) else image.to_rgba()
    return _gray(lightness(rgba), rgba[..., 3])


def value_map(image: Image | U8, levels: int = 5) -> U8:
    """Lightness posterized into `levels` equal bands, drawn as flat grays (0 to 255)."""
    if levels < 2:
        raise ValueError("levels must be >= 2")
    rgba = image if isinstance(image, np.ndarray) else image.to_rgba()
    band = np.minimum((lightness(rgba) * levels).astype(np.int64), levels - 1)
    return _gray(band / (levels - 1), rgba[..., 3])


def overlay(
    image: Image | U8,
    mask: Mask,
    color: tuple[int, int, int] = (255, 0, 255),
    opacity: float = 0.5,
) -> U8:
    """Tint the pixels inside `mask` with `color` at `opacity`; others unchanged."""
    rgba = image if isinstance(image, np.ndarray) else image.to_rgba()
    if mask.shape != rgba.shape[:2]:
        raise ValueError("mask shape must match the image")
    if not 0.0 <= opacity <= 1.0:
        raise ValueError("opacity must be in [0, 1]")
    out = rgba.copy()
    tint = np.array(color, dtype=np.float64)
    blended = rgba[..., :3].astype(np.float64) * (1 - opacity) + tint * opacity
    out[..., :3][mask] = np.rint(blended[mask]).astype(np.uint8)
    return out
