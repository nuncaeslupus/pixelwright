"""`palette` (R-PIX-1): every pixel in the palette; distinct colors within budget."""

from __future__ import annotations

import numpy as np

from pixelwright.core.checks.base import CheckResult, tile_boxes
from pixelwright.core.image import Image, IndexedImage
from pixelwright.core.palette import Palette


def check_palette(image: Image, palette: Palette, budget: int | None = None) -> CheckResult:
    rgba = image.to_rgba()
    opaque = rgba[..., 3] > 0
    rgb = rgba[..., :3].astype(np.int64)
    keys = (rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2]
    pal = palette.rgb_array().astype(np.int64)
    allowed = (pal[:, 0] << 16) | (pal[:, 1] << 8) | pal[:, 2]
    off = opaque & ~np.isin(keys, allowed)
    total = int(opaque.sum())
    share = 1.0 if total == 0 else 1.0 - int(off.sum()) / total
    distinct = (
        len(np.unique(image.indices[image.opaque()]))
        if isinstance(image, IndexedImage)
        else len(np.unique(keys[opaque]))
    )
    status = "fail" if share < 1.0 else "pass"
    if status == "pass" and budget is not None and distinct > budget:
        status = "warn"
    return CheckResult(
        "palette",
        "R-PIX-1",
        status,
        share,
        1.0,
        tile_boxes(off),
        {"off_palette_pixels": int(off.sum()), "distinct_colors": distinct, "budget": budget},
    )
