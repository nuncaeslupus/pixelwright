"""`banding` (R-PIX-5): thin bands of one color tracing the border between a darker and a
lighter color, the contour-line shading that flattens forms."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from pixelwright.core.checks.base import Box, CheckResult
from pixelwright.core.checks.regions import bbox, label
from pixelwright.core.image import IndexedImage

MAX_WIDTH = 2


def _band_pixels(
    idx: npt.NDArray[np.int64], light: npt.NDArray[np.float64]
) -> npt.NDArray[np.bool_]:
    """Pixels in runs of <= MAX_WIDTH between a darker and a lighter color (rows or columns)."""
    out = np.zeros(idx.shape, dtype=bool)
    for grid, view in ((idx, out), (idx.T, out.T)):
        for r in range(grid.shape[0]):
            row = grid[r]
            change = np.flatnonzero(np.diff(row)) + 1
            starts = np.concatenate([[0], change])
            ends = np.concatenate([change, [len(row)]])
            for i in range(1, len(starts) - 1):
                a, b = starts[i], ends[i]
                if b - a > MAX_WIDTH or row[a] < 0:
                    continue
                left, mid, right = row[a - 1], row[a], row[b]
                if left < 0 or right < 0:
                    continue
                la, lm, lr = light[left], light[mid], light[right]
                if (la < lm < lr) or (la > lm > lr):
                    view[r, a:b] = True
    return out


def check_banding(image: IndexedImage, max_length: int = 12) -> CheckResult:
    """Warn when a band runs longer than `max_length` pixels."""
    idx = np.where(image.opaque(), image.indices.astype(np.int64), -1)
    light = image.palette.oklab()[:, 0]
    bands = _band_pixels(idx, light)
    regions: list[Box] = []
    longest = 0
    for color in np.unique(idx[bands]):
        labels, n = label(bands & (idx == color))
        for i in range(1, n + 1):
            comp = labels == i
            x, y, w, h = bbox(comp)
            length = max(w, h)
            longest = max(longest, length)
            if length > max_length:
                regions.append((x, y, w, h))
    return CheckResult(
        "banding",
        "R-PIX-5",
        "warn" if regions else "pass",
        float(longest),
        float(max_length),
        tuple(regions),
        {"bands": len(regions)},
    )
