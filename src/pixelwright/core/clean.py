"""`clean`: remove orphan pixels and 2-pixel noise clusters, only inside a mask.

Each offending pixel takes the most common color among its 8 neighbours (transparency
counts as a color); ties go to the neighbour color nearest in OKLab to the pixel's own.
Pixels outside the mask are never changed.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from pixelwright.core.checks.orphans import orphan_mask, pair_mask
from pixelwright.core.image import IndexedImage, Mask

TRANSPARENT = -1


@dataclass(frozen=True)
class CleanReport:
    changed: int
    orphans_before: int
    orphans_after: int  # inside the mask
    pairs_removed: int


def _replacement(key: npt.NDArray[np.int64], y: int, x: int, lab: npt.NDArray[np.float64]) -> int:
    h, w = key.shape
    neighbours = [
        int(key[ny, nx])
        for ny in range(max(0, y - 1), min(h, y + 2))
        for nx in range(max(0, x - 1), min(w, x + 2))
        if (ny, nx) != (y, x)
    ]
    counts = Counter(neighbours).most_common()
    top = [c for c, n in counts if n == counts[0][1]]
    own = int(key[y, x])
    if len(top) == 1 or own == TRANSPARENT:
        return top[0]

    def distance(c: int) -> float:
        return float("inf") if c == TRANSPARENT else float(np.linalg.norm(lab[c] - lab[own]))

    return min(top, key=lambda c: (distance(c), c))


def clean(
    image: IndexedImage,
    mask: Mask | None = None,
    *,
    pairs: bool = False,
    max_passes: int = 5,
) -> tuple[IndexedImage, CleanReport]:
    """Return a cleaned copy of `image` and what changed. `mask=None` means everywhere."""
    region = np.ones(image.indices.shape, bool) if mask is None else mask
    if region.shape != image.indices.shape:
        raise ValueError("mask shape must match the image")
    lab = image.palette.oklab()
    key = np.where(image.opaque(), image.indices.astype(np.int64), TRANSPARENT)
    original = key.copy()
    before = int((orphan_mask(image) & region).sum())
    pairs_removed = 0
    current = image
    for _ in range(max_passes):
        targets = orphan_mask(current) & region
        if pairs:
            found = pair_mask(current) & region
            pairs_removed += int(found.sum())
            targets |= found
        if not targets.any():
            break
        snapshot = key.copy()
        for y, x in zip(*np.nonzero(targets), strict=True):
            key[y, x] = _replacement(snapshot, int(y), int(x), lab)
        current = _rebuild(image, key)
    after = int((orphan_mask(current) & region).sum())
    changed = int((key != original).sum())
    return current, CleanReport(changed, before, after, pairs_removed)


def _rebuild(image: IndexedImage, key: npt.NDArray[np.int64]) -> IndexedImage:
    opaque = key != TRANSPARENT
    indices = np.where(opaque, key, 0).astype(np.uint16)
    return IndexedImage(indices, image.palette, None if opaque.all() else opaque)
