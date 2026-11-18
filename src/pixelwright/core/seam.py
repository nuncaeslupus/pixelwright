"""Join two overlapping images along the vertical seam where they differ least.

Blending two pixel-art tiles would invent colours; a cut keeps every pixel from one tile or
the other. The seam is the minimum-cost top-to-bottom path through the overlap (dynamic
programming, one column step per row at most), the way image quilting joins patches.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from pixelwright.core.color import srgb8_to_oklab

Arr = npt.NDArray[np.uint8]


def seam_path(left: Arr, right: Arr) -> npt.NDArray[np.int64]:
    """For each row, the first overlap column taken from `right` (both are H x W x C)."""
    lab = [srgb8_to_oklab(t[..., :3]) for t in (left, right)]
    cost = np.linalg.norm(lab[0] - lab[1], axis=-1)
    if left.shape[-1] == 4:  # a transparent pixel on either side costs nothing to cut through
        cost[(left[..., 3] == 0) | (right[..., 3] == 0)] = 0.0
    h, w = cost.shape
    acc = cost.copy()
    for y in range(1, h):
        prev = acc[y - 1]
        best = prev.copy()
        best[1:] = np.minimum(best[1:], prev[:-1])
        best[:-1] = np.minimum(best[:-1], prev[1:])
        acc[y] += best
    path = np.empty(h, np.int64)
    path[-1] = int(np.argmin(acc[-1]))
    for y in range(h - 2, -1, -1):
        x = path[y + 1]
        lo, hi = max(0, x - 1), min(w, x + 2)
        path[y] = lo + int(np.argmin(acc[y, lo:hi]))
    return path


def join(left: Arr, right: Arr, overlap: int) -> Arr:
    """`left` and `right` side by side, sharing `overlap` columns cut along the best seam."""
    if left.shape[0] != right.shape[0] or left.shape[2:] != right.shape[2:]:
        raise ValueError("tiles to join need the same height and channels")
    if overlap <= 0:
        return np.concatenate([left, right], axis=1)
    overlap = min(overlap, left.shape[1], right.shape[1])
    a, b = left[:, -overlap:], right[:, :overlap]
    path = seam_path(a, b)
    cols = np.arange(overlap)[None, :]
    mid = np.where((cols >= path[:, None])[..., None], b, a)
    return np.concatenate([left[:, :-overlap], mid, right[:, overlap:]], axis=1)
