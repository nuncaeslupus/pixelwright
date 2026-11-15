"""`orphans` (R-PIX-3): pixels with no same-colored 8-neighbour, and 2-pixel clusters."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from pixelwright.core.checks.base import CheckResult, pixel_boxes, tile_boxes
from pixelwright.core.image import IndexedImage

OFFSETS = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0)]


def same_neighbours(image: IndexedImage) -> npt.NDArray[np.int64]:
    """Per pixel, how many of its 8 neighbours are opaque with the same index."""
    idx = image.indices.astype(np.int64)
    opaque = image.opaque()
    key = np.where(opaque, idx, -1)
    pad = np.pad(key, 1, constant_values=-2)
    h, w = key.shape
    count = np.zeros((h, w), dtype=np.int64)
    for dy, dx in OFFSETS:
        count += pad[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w] == key
    return np.where(opaque, count, 8)


def orphan_mask(image: IndexedImage) -> npt.NDArray[np.bool_]:
    mask: npt.NDArray[np.bool_] = same_neighbours(image) == 0
    return mask


def pair_mask(image: IndexedImage) -> npt.NDArray[np.bool_]:
    """Pixels in a cluster of exactly two (each has one same neighbour: the other)."""
    n = same_neighbours(image)
    one = n == 1
    pad = np.pad(one, 1, constant_values=False)
    key = np.where(image.opaque(), image.indices.astype(np.int64), -1)
    kpad = np.pad(key, 1, constant_values=-2)
    h, w = key.shape
    partner_single = np.zeros((h, w), dtype=bool)
    for dy, dx in OFFSETS:
        same = kpad[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w] == key
        partner_single |= same & pad[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
    pairs: npt.NDArray[np.bool_] = one & partner_single
    return pairs


def check_orphans(image: IndexedImage, max_orphans: int = 0) -> CheckResult:
    orphans = orphan_mask(image)
    pairs = pair_mask(image)
    count = int(orphans.sum())
    per_tile = [
        int(orphans[y : y + 16, x : x + 16].sum())
        for y in range(0, image.height, 16)
        for x in range(0, image.width, 16)
    ]
    return CheckResult(
        "orphans",
        "R-PIX-3",
        "warn" if count > max_orphans else "pass",
        float(count),
        float(max_orphans),
        pixel_boxes(orphans),
        {
            "pairs": int(pairs.sum()) // 2,
            "pair_tiles": [list(b) for b in tile_boxes(pairs)],
            "max_per_tile": max(per_tile, default=0),
        },
    )
