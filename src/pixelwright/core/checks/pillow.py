"""`pillow` (R-PIX-6): shading must follow the light, not the outline.

Pillow shading darkens toward every edge, so lightness tracks distance-to-edge instead of
the projection on the light direction. Both correlations are measured over the subject.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from pixelwright.core.checks.base import CheckResult
from pixelwright.core.checks.regions import bbox
from pixelwright.core.checks.shape import edge_distance, subject_mask
from pixelwright.core.image import Image
from pixelwright.core.render import lightness

MARGIN = 0.15
MIN_EDGE_CORR = 0.4


def _corr(a: npt.NDArray[np.float64], b: npt.NDArray[np.float64]) -> float:
    if a.std() < 1e-9 or b.std() < 1e-9:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def check_pillow(image: Image, light: tuple[float, float] = (-0.6, -0.8)) -> CheckResult:
    """`light` points from the subject toward the light, in image axes (x right, y down)."""
    mask = subject_mask(image)
    if mask.sum() < 16:
        return CheckResult("pillow", "R-PIX-6", "pass", 0.0, MARGIN, (), {"reason": "too small"})
    values = lightness(image.to_rgba())[mask]
    ys, xs = np.nonzero(mask)
    lx, ly = light
    norm = float(np.hypot(lx, ly)) or 1.0
    proj = ((xs - xs.mean()) * lx + (ys - ys.mean()) * ly) / norm
    dist = edge_distance(mask)[mask].astype(np.float64)
    r_light, r_edge = _corr(values, proj), _corr(values, dist)
    dominates = r_edge > MIN_EDGE_CORR and r_edge > abs(r_light) + MARGIN
    return CheckResult(
        "pillow",
        "R-PIX-6",
        "fail" if dominates else "pass",
        r_edge - abs(r_light),
        MARGIN,
        (bbox(mask),) if dominates else (),
        {"r_light": r_light, "r_edge": r_edge},
    )
