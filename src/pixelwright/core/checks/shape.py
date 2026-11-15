"""Sprite-shape helpers: subject mask, boundary, distance to edge."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from pixelwright.core.image import Image, IndexedImage

BoolArray = npt.NDArray[np.bool_]


def subject_mask(image: Image) -> BoolArray:
    """Opaque pixels; without transparency, pixels unlike the most common border color."""
    rgba = image.to_rgba()
    opaque = rgba[..., 3] > 0
    if not opaque.all():
        return opaque
    key = (
        image.indices.astype(np.int64)
        if isinstance(image, IndexedImage)
        else (rgba[..., 0].astype(np.int64) << 16)
        | (rgba[..., 1].astype(np.int64) << 8)
        | rgba[..., 2]
    )
    border = np.concatenate([key[0], key[-1], key[:, 0], key[:, -1]])
    values, counts = np.unique(border, return_counts=True)
    mask: BoolArray = key != values[int(np.argmax(counts))]
    return mask


def erode(mask: BoolArray) -> BoolArray:
    pad = np.pad(mask, 1, constant_values=False)
    out: BoolArray = mask & pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
    return out


def boundary(mask: BoolArray) -> BoolArray:
    out: BoolArray = mask & ~erode(mask)
    return out


def edge_distance(mask: BoolArray) -> npt.NDArray[np.int64]:
    """4-connected distance (in pixels, from 1) of each mask pixel to the mask's edge."""
    dist = np.zeros(mask.shape, dtype=np.int64)
    current = mask.copy()
    while current.any():
        dist[current] += 1
        current = erode(current)
    return dist


def ring(mask: BoolArray, width: int = 3) -> BoolArray:
    """Pixels outside `mask` within `width` pixels of it (8-connected dilation)."""
    grown = mask.copy()
    for _ in range(width):
        pad = np.pad(grown, 1, constant_values=False)
        h, w = mask.shape
        grown = np.zeros_like(mask)
        for dy in range(3):
            for dx in range(3):
                grown |= pad[dy : dy + h, dx : dx + w]
    out: BoolArray = grown & ~mask
    return out
