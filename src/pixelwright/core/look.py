"""Measure an image's look, and repaint one material with another ramp.

`measure` gives the numbers a style is judged by (scene norms 33-35): how many colours,
how dark, how saturated, how many isolated pixels, and how big the steps between
neighbouring colours are (small steps read as smooth gradients).

`recolor` swaps the colours of one material (the pixels a mask selects) for a ramp,
keeping each pixel's place between the material's darkest and lightest tone, so light
and relief survive the change.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt

from pixelwright.core.color import srgb8_to_oklab

U8 = npt.NDArray[np.uint8]
Mask = npt.NDArray[np.bool_]

OPAQUE = 128  # alpha at or above which a pixel counts
LOW, HIGH = 2.0, 98.0  # percentiles that bound a material's lightness (ignore stray pixels)


def _key(rgb: U8) -> npt.NDArray[np.int64]:
    """One integer per RGB colour."""
    c = rgb.astype(np.int64)
    return (c[..., 0] << 16) | (c[..., 1] << 8) | c[..., 2]


def measure(rgba: U8) -> dict[str, Any]:
    """The look of an RGBA image, counting opaque pixels only."""
    opaque = rgba[..., 3] >= OPAQUE
    if not opaque.any():
        raise ValueError("the image has no opaque pixels")
    key = _key(rgba[..., :3])
    lab = srgb8_to_oklab(rgba[..., :3][opaque])
    chroma = np.hypot(lab[:, 1], lab[:, 2])

    pad = np.pad(key, 1, constant_values=-1)
    centre = pad[1:-1, 1:-1]
    neighbours = [pad[:-2, 1:-1], pad[2:, 1:-1], pad[1:-1, :-2], pad[1:-1, 2:]]
    alone = np.logical_and.reduce([n != centre for n in neighbours]) & opaque

    full = srgb8_to_oklab(rgba[..., :3])
    steps = []
    for a, b, oa, ob in (
        (full[:, 1:], full[:, :-1], opaque[:, 1:], opaque[:, :-1]),
        (full[1:], full[:-1], opaque[1:], opaque[:-1]),
    ):
        d = np.linalg.norm(a - b, axis=-1)[oa & ob]
        steps.append(d[d > 1e-6])
    edge = np.concatenate(steps) * 100.0
    return {
        "pixels": int(opaque.sum()),
        "colors": int(np.unique(key[opaque]).size),
        "lightness": {
            "median": round(float(np.median(lab[:, 0])), 3),
            "p10": round(float(np.percentile(lab[:, 0], 10)), 3),
            "p90": round(float(np.percentile(lab[:, 0], 90)), 3),
        },
        "chroma_median": round(float(np.median(chroma)), 3),
        "isolated": round(float(alone.sum() / opaque.sum()), 4),
        "step_median": round(float(np.median(edge)), 1) if edge.size else 0.0,
    }


def recolor(rgba: U8, mask: Mask, ramp: list[tuple[int, int, int]], light: float = 0.0) -> U8:
    """`rgba` with the masked pixels repainted from `ramp`.

    A pixel keeps its relative place between the material's darkest and lightest tone
    (percentiles 2 and 98) and takes the ramp shade at that place; `light` (-1..1) moves
    every pixel that share of the ramp towards light (positive) or dark (negative).
    """
    if len(ramp) < 2:
        raise ValueError("a ramp needs at least 2 shades")
    if mask.shape != rgba.shape[:2]:
        raise ValueError(f"mask {mask.shape} does not match the image {rgba.shape[:2]}")
    sel = mask & (rgba[..., 3] >= OPAQUE)
    out = rgba.copy()
    if not sel.any():
        return out
    shades = np.array(ramp, np.uint8)
    order = np.argsort(srgb8_to_oklab(shades)[:, 0])
    shades = shades[order]
    lum = srgb8_to_oklab(rgba[..., :3][sel])[:, 0]
    lo, hi = np.percentile(lum, LOW), np.percentile(lum, HIGH)
    t = np.zeros_like(lum) if hi - lo < 1e-6 else np.clip((lum - lo) / (hi - lo), 0.0, 1.0)
    t = np.clip(t + light, 0.0, 1.0)
    idx = np.rint(t * (len(shades) - 1)).astype(np.int64)
    out[..., :3][sel] = shades[idx]
    return out


def mask_from(rgba: U8, color: tuple[int, int, int] | None = None) -> Mask:
    """The pixels of a mask image: those of `color` if given, else every opaque, non-black one."""
    opaque = rgba[..., 3] >= OPAQUE
    if color is not None:
        return opaque & np.all(rgba[..., :3] == np.array(color, np.uint8), axis=-1)
    return opaque & (rgba[..., :3].max(axis=-1) > 0)
