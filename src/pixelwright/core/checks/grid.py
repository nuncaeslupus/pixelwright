"""`grid` (R-PIX-1): an upscaled export is made of uniform scale x scale blocks."""

from __future__ import annotations

from pixelwright.core.checks.base import CheckResult, pixel_boxes
from pixelwright.core.image import Image


def check_grid(upscaled: Image, scale: int) -> CheckResult:
    if scale < 1:
        raise ValueError("scale must be >= 1")
    rgba = upscaled.to_rgba()
    h, w = rgba.shape[:2]
    if h % scale or w % scale:
        return CheckResult(
            "grid", "R-PIX-1", "fail", float(h * w), 0.0, (), {"reason": "size not a multiple"}
        )
    blocks = rgba.reshape(h // scale, scale, w // scale, scale, 4)
    bad = (blocks != blocks[:, :1, :, :1, :]).any(axis=(1, 3, 4))
    count = int(bad.sum())
    return CheckResult(
        "grid",
        "R-PIX-1",
        "fail" if count else "pass",
        float(count),
        0.0,
        pixel_boxes(bad),
        {"scale": scale},
    )
