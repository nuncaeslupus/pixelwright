"""How much each colour matters where it is, before any palette is chosen.

A global palette (median cut, k-means) spends its entries on large areas: a sky gradient
gets six shades and a lit window, a few dozen pixels, gets none. But a small colour that
stands out from its surroundings (a window glow, the moon, an eye) is often what the
image is about. This module measures that, per pixel and per colour group:

- *local contrast*: OKLab distance from a pixel to the mean of its neighbourhood;
- *rarity*: how little of the image shares the pixel's colour (coarse OKLab bins);
- *importance* = local contrast x rarity, normalised to 0-1.

`analyze_colors` groups the image's colours and reports, for each group, its area share
and importance, and flags *accents*: groups with high importance but little area.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from pixelwright.core.color import FloatArray, oklab_to_oklch, oklab_to_srgb8, srgb8_to_oklab
from pixelwright.core.image import RGBImage

ALPHA_THRESHOLD = 128
BIN = 0.04  # OKLab bin size for rarity: about one just-noticeable step in lightness
ACCENT_AREA = 0.02  # an accent covers at most this share of the opaque pixels


def _box_mean(lab: FloatArray, radius: int) -> FloatArray:
    """Mean of each pixel's (2r+1)^2 neighbourhood, edges clamped (summed-area table)."""
    pad = np.pad(lab, ((radius + 1, radius), (radius + 1, radius), (0, 0)), mode="edge")
    sat = pad.cumsum(0).cumsum(1)
    k = 2 * radius + 1
    h, w = lab.shape[:2]
    total = sat[k : k + h, k : k + w] - sat[:h, k : k + w] - sat[k : k + h, :w] + sat[:h, :w]
    out: FloatArray = total / (k * k)
    return out


def _bins(lab: FloatArray) -> npt.NDArray[np.int64]:
    q = np.floor(lab / BIN).astype(np.int64)
    q -= q.reshape(-1, 3).min(axis=0)
    span = q.reshape(-1, 3).max(axis=0) + 1
    key: npt.NDArray[np.int64] = (q[..., 0] * span[1] + q[..., 1]) * span[2] + q[..., 2]
    return key


def importance_map(image: RGBImage, radius: int | None = None) -> FloatArray:
    """Per-pixel importance in 0-1 (transparent pixels get 0)."""
    rgba = image.rgba
    lab = srgb8_to_oklab(rgba[..., :3])
    opaque = rgba[..., 3] >= ALPHA_THRESHOLD
    h, w = opaque.shape
    radius = radius or max(2, round(min(h, w) * 0.03))
    contrast = np.sqrt(((lab - _box_mean(lab, radius)) ** 2).sum(axis=2))
    key = _bins(lab)
    _, inverse, counts = np.unique(key[opaque], return_inverse=True, return_counts=True)
    share = np.zeros(opaque.shape)
    share[opaque] = counts[inverse.reshape(-1)] / max(1, int(opaque.sum()))
    rarity = 1.0 - np.sqrt(share)  # 1 for a one-off colour, 0 for a single-colour image
    score = np.where(opaque, contrast * rarity, 0.0)
    top = float(np.percentile(score[opaque], 99.5)) if opaque.any() else 0.0
    out: FloatArray = np.clip(score / top, 0.0, 1.0) if top > 0 else score
    return out


@dataclass(frozen=True)
class ColorGroup:
    color: tuple[int, int, int]  # mean colour of the group, sRGB
    share: float  # of the opaque pixels
    importance: float  # mean pixel importance, 0-1
    accent: bool  # important but small: worth its own palette entry
    lightness: float  # OKLCh L, 0-1
    chroma: float  # OKLCh C


def analyze_colors(image: RGBImage, imp: FloatArray | None = None) -> list[ColorGroup]:
    """Colour groups (coarse OKLab bins merged with their neighbours), most important first."""
    rgba = image.rgba
    opaque = rgba[..., 3] >= ALPHA_THRESHOLD
    if not opaque.any():
        return []
    imp = importance_map(image) if imp is None else imp
    lab = srgb8_to_oklab(rgba[..., :3])[opaque]
    weights = imp[opaque]
    key = np.floor(lab / (2 * BIN)).astype(np.int64)
    uniq, inverse = np.unique(key, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    n = len(uniq)
    counts = np.bincount(inverse, minlength=n).astype(np.float64)
    mean_lab = np.stack([np.bincount(inverse, lab[:, c], n) for c in range(3)], 1) / counts[:, None]
    mean_imp = np.bincount(inverse, weights, n) / counts
    total = float(opaque.sum())
    lch = oklab_to_oklch(mean_lab)
    rgb = oklab_to_srgb8(mean_lab)
    cut = float(np.percentile(mean_imp, 90)) if n > 10 else float(mean_imp.max())
    groups = [
        ColorGroup(
            color=(int(rgb[i, 0]), int(rgb[i, 1]), int(rgb[i, 2])),
            share=float(counts[i] / total),
            importance=float(mean_imp[i]),
            accent=bool(
                mean_imp[i] >= cut and counts[i] / total <= ACCENT_AREA and mean_imp[i] > 0.2
            ),
            lightness=float(lch[i, 0]),
            chroma=float(lch[i, 1]),
        )
        for i in range(n)
    ]
    return sorted(groups, key=lambda g: g.importance * np.sqrt(g.share), reverse=True)
