"""Regularise jaggy 1-px lines (R-PIX-4) into clean pixel-art steps.

A straight pixel line steps in equal runs (3,3,3) or alternates two neighbouring lengths
(2,1,2,1). Lines that come out of a generator or a reduction often step 1,2,1,3,1. For
each line `check_line_runs` would flag that is close to straight, `regularise_lines`
redraws it between the same ends with clean runs; the pixels it leaves take the colour
most common around them. Curves are left alone.
"""

from __future__ import annotations

from collections import Counter

import numpy as np
import numpy.typing as npt

from pixelwright.core.checks.line_runs import _l_corners, _runs, line_components, runs_are_clean
from pixelwright.core.image import IndexedImage

STRAIGHT = 1.0  # max distance (px) of a line pixel from its chord to count as straight


def clean_runs(length: int, steps: int) -> list[int]:
    """Run lengths covering `length` pixels in `steps` runs: all equal when the ratio is
    near a whole number, else alternating the two neighbouring lengths."""
    avg = length / steps
    lo = int(np.floor(avg))
    whole = abs(avg - round(avg)) < 0.25 or lo == 0
    pattern = [max(1, round(avg))] if whole else [lo + 1, lo]
    runs: list[int] = []
    while sum(runs) < length:
        runs.append(pattern[len(runs) % len(pattern)])
    runs[-1] -= sum(runs) - length
    return [r for r in runs if r > 0]


def _redraw(comp: npt.NDArray[np.bool_]) -> npt.NDArray[np.bool_] | None:
    """The same line with clean runs, or None if it is not close to straight."""
    ys, xs = np.nonzero(comp)
    horizontal = np.ptp(xs) >= np.ptp(ys)
    major, minor = (xs, ys) if horizontal else (ys, xs)
    a, b = int(np.argmin(major)), int(np.argmax(major))
    p0, p1 = np.array([major[a], minor[a]], float), np.array([major[b], minor[b]], float)
    chord = p1 - p0
    if np.hypot(*chord) == 0:
        return None
    pts = np.stack([major, minor], 1).astype(float) - p0
    dist = np.abs(pts[:, 0] * chord[1] - pts[:, 1] * chord[0]) / np.hypot(*chord)
    if dist.max() > STRAIGHT:
        return None
    length = int(major[b] - major[a]) + 1
    steps = abs(int(minor[b] - minor[a])) + 1
    sign = 1 if minor[b] >= minor[a] else -1
    out = np.zeros_like(comp)
    m, n = int(major[a]), int(minor[a])
    for run in clean_runs(length, steps):
        for i in range(run):
            y, x = (n, m + i) if horizontal else (m + i, n)
            if 0 <= y < out.shape[0] and 0 <= x < out.shape[1]:
                out[y, x] = True
        m, n = m + run, n + sign
    return out


def regularise_lines(image: IndexedImage) -> tuple[IndexedImage, int]:
    """Redraw near-straight jaggy lines with clean runs; returns the image and how many
    lines changed."""
    key = image.indices.astype(np.int64).copy()
    h, w = key.shape
    fixed = 0
    for comp in line_components(image):
        if not _l_corners(comp).any() and runs_are_clean(_runs(comp)):
            continue
        new = _redraw(comp)
        if new is None or (new == comp).all():
            continue
        colour = int(key[comp][0])
        for y, x in zip(*np.nonzero(comp & ~new), strict=True):
            around = Counter(
                int(key[ny, nx])
                for ny in range(max(0, y - 1), min(h, y + 2))
                for nx in range(max(0, x - 1), min(w, x + 2))
                if not comp[ny, nx] and key[ny, nx] != colour
            )
            if around:
                key[y, x] = around.most_common(1)[0][0]
        key[new] = colour
        fixed += 1
    return IndexedImage(key.astype(image.indices.dtype), image.palette, image.alpha), fixed
