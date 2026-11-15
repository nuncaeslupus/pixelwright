"""`focal-contrast` (R-VAL-1): the strongest local contrast sits inside the focal mask."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from pixelwright.core.checks.base import CheckResult
from pixelwright.core.image import Image
from pixelwright.core.render import lightness


def local_contrast(image: Image, window: int = 8) -> tuple[npt.NDArray[np.float64], int]:
    """RMS contrast of OKLab L per `window` x `window` tile (tiles cover the image)."""
    values = lightness(image.to_rgba())
    h, w = values.shape
    th, tw = -(-h // window), -(-w // window)
    out = np.zeros((th, tw))
    for ty in range(th):
        for tx in range(tw):
            tile = values[ty * window : (ty + 1) * window, tx * window : (tx + 1) * window]
            out[ty, tx] = float(tile.std())
    return out, window


def check_focal_contrast(
    image: Image, focal: npt.NDArray[np.bool_], window: int = 8
) -> CheckResult:
    if focal.shape != (image.height, image.width):
        raise ValueError("focal mask must match the image")
    contrast, win = local_contrast(image, window)
    th, tw = contrast.shape
    inside = np.zeros((th, tw), dtype=bool)
    for ty in range(th):
        for tx in range(tw):
            tile = focal[ty * win : (ty + 1) * win, tx * win : (tx + 1) * win]
            inside[ty, tx] = bool(tile.mean() >= 0.5) if tile.size else False
    max_in = float(contrast[inside].max()) if inside.any() else 0.0
    max_out = float(contrast[~inside].max()) if (~inside).any() else 0.0
    regions: tuple[tuple[int, int, int, int], ...] = ()
    if max_out > max_in:
        flat = int(np.argmax(np.where(~inside, contrast, -1)))
        row, col = divmod(flat, tw)
        regions = ((col * win, row * win, win, win),)
    ratio = max_in / max_out if max_out > 0 else float("inf") if max_in > 0 else 1.0
    return CheckResult(
        "focal-contrast",
        "R-VAL-1",
        "warn" if max_out > max_in else "pass",
        ratio,
        1.0,
        regions,
        {"max_inside": max_in, "max_outside": max_out, "window": win},
    )
