"""`line-runs` (R-PIX-4): 1-px lines should step in regular runs, without L-corners.

A clean pixel line is a staircase whose run lengths change monotonically (a curve) or
repeat a short pattern (a straight slope): 1,1,2,2,3 or 2,1,2,1. Irregular sequences
such as 2,1,3,1 read as jaggies. L-corners are steps where the line doubles up (three
pixels of a 2x2 block on the line).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

from pixelwright.core.checks.base import Box, CheckResult
from pixelwright.core.checks.regions import N8, bbox, label
from pixelwright.core.image import IndexedImage

MIN_LINE = 6  # pixels; shorter strokes are details, not lines


def runs_are_clean(runs: Sequence[int]) -> bool:
    """True if the interior runs are monotonic or repeat a pattern of period <= 2."""
    inner = list(runs[1:-1]) if len(runs) > 3 else list(runs)
    if len(inner) < 3:
        return True
    diffs = np.diff(inner)
    if (diffs >= 0).all() or (diffs <= 0).all():
        return True
    return all(inner[i] == inner[i - 2] for i in range(2, len(inner)))


def _same_count(key: npt.NDArray[np.int64]) -> npt.NDArray[np.int64]:
    h, w = key.shape
    pad = np.pad(key, 1, constant_values=-2)
    out = np.zeros((h, w), dtype=np.int64)
    for dy, dx in N8:
        out += pad[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w] == key
    return out


def _l_corners(component: npt.NDArray[np.bool_]) -> npt.NDArray[np.bool_]:
    """Pixels in a 2x2 block with exactly three line pixels (the doubled corner)."""
    c = component.astype(np.int64)
    s = c[:-1, :-1] + c[1:, :-1] + c[:-1, 1:] + c[1:, 1:]
    out = np.zeros_like(component)
    three = s == 3
    for dy in (0, 1):
        for dx in (0, 1):
            out[dy : dy + three.shape[0], dx : dx + three.shape[1]] |= three
    return out & component


def _runs(component: npt.NDArray[np.bool_]) -> list[int]:
    """Run lengths along the line's major axis (one run per row or column it spans)."""
    x, y, w, h = bbox(component)
    sub = component[y : y + h, x : x + w]
    counts = sub.sum(axis=1) if w >= h else sub.sum(axis=0)
    return [int(v) for v in counts if v > 0]


def line_components(image: IndexedImage) -> list[npt.NDArray[np.bool_]]:
    """Thin (1-px) strokes: per color, pixels with at most 3 same-color neighbours, grouped."""
    key = np.where(image.opaque(), image.indices.astype(np.int64), -1)
    thin = (_same_count(key) <= 3) & image.opaque()  # 3 keeps doubled corners
    out = []
    for color in np.unique(key[thin]):
        labels, n = label(thin & (key == color))
        for i in range(1, n + 1):
            comp = labels == i
            if comp.sum() >= MIN_LINE:
                out.append(comp)
    return out


def check_line_runs(image: IndexedImage, max_bad: int = 0) -> CheckResult:
    bad: list[Box] = []
    corners = 0
    jaggy = 0
    for comp in line_components(image):
        lc = int(_l_corners(comp).sum())
        corners += lc
        clean = runs_are_clean(_runs(comp))
        jaggy += not clean
        if lc or not clean:
            bad.append(bbox(comp))
    return CheckResult(
        "line-runs",
        "R-PIX-4",
        "warn" if len(bad) > max_bad else "pass",
        float(len(bad)),
        float(max_bad),
        tuple(bad),
        {"jaggy_segments": jaggy, "l_corner_pixels": corners},
    )
