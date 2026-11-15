"""Small image helpers shared by detectors: 8-connected labelling and same-color counts."""

from __future__ import annotations

from collections import deque

import numpy as np
import numpy.typing as npt

N8 = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0)]


def label(mask: npt.NDArray[np.bool_]) -> tuple[npt.NDArray[np.int64], int]:
    """8-connected components of `mask`: (labels with 0 = background, count)."""
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int64)
    count = 0
    for y, x in zip(*np.nonzero(mask), strict=True):
        if labels[y, x]:
            continue
        count += 1
        labels[y, x] = count
        queue = deque([(int(y), int(x))])
        while queue:
            cy, cx = queue.popleft()
            for dy, dx in N8:
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not labels[ny, nx]:
                    labels[ny, nx] = count
                    queue.append((ny, nx))
    return labels, count


def bbox(mask: npt.NDArray[np.bool_]) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(mask)
    return int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)
