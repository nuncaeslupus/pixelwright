"""`value-groups` (R-VAL-1): how many lightness groups read in the image (k-means on L)."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from pixelwright.core.checks.base import CheckResult
from pixelwright.core.image import Image
from pixelwright.core.render import lightness

MAX_K = 8
SAMPLE = 3000


def _kmeans_1d(values: npt.NDArray[np.float64], k: int) -> npt.NDArray[np.float64]:
    # Spread the start over distinct values so small groups still get a center.
    centers = np.quantile(np.unique(values), (np.arange(k) + 0.5) / k)
    for _ in range(50):
        labels = np.abs(values[:, None] - centers[None]).argmin(axis=1)
        moved = np.array(
            [values[labels == i].mean() if (labels == i).any() else centers[i] for i in range(k)]
        )
        if np.allclose(moved, centers):
            break
        centers = moved
    return np.sort(centers)


def _silhouette(values: npt.NDArray[np.float64], labels: npt.NDArray[np.intp], k: int) -> float:
    d = np.abs(values[:, None] - values[None, :])
    scores = []
    for i in range(k):
        own = labels == i
        if own.sum() < 2:
            continue
        a = d[own][:, own].sum(axis=1) / (own.sum() - 1)
        b = np.full(int(own.sum()), np.inf)
        for j in range(k):
            other = labels == j
            if j != i and other.any():
                b = np.minimum(b, d[own][:, other].mean(axis=1))
        scores.append(((b - a) / np.maximum(np.maximum(a, b), 1e-12)).sum())
    return float(np.sum(scores) / len(values))


def check_value_groups(image: Image, max_groups: int = 5) -> CheckResult:
    rgba = image.to_rgba()
    values = lightness(rgba)[rgba[..., 3] > 0]
    if values.size == 0:
        return CheckResult("value-groups", "R-VAL-1", "pass", 0.0, float(max_groups))
    rng = np.random.default_rng(0)
    sample = values if values.size <= SAMPLE else rng.choice(values, SAMPLE, replace=False)
    best_k, best_s, best_centers = 1, -1.0, np.array([float(values.mean())])
    if np.ptp(sample) > 1e-3:
        for k in range(2, min(MAX_K, len(np.unique(sample))) + 1):
            centers = _kmeans_1d(sample, k)
            labels = np.abs(sample[:, None] - centers[None]).argmin(axis=1)
            s = _silhouette(sample, labels, k)
            if s > best_s + 1e-6:
                best_k, best_s, best_centers = k, s, centers
    labels = np.abs(values[:, None] - best_centers[None]).argmin(axis=1)
    shares = [float((labels == i).mean()) for i in range(best_k)]
    return CheckResult(
        "value-groups",
        "R-VAL-1",
        "warn" if best_k > max_groups else "pass",
        float(best_k),
        float(max_groups),
        (),
        {
            "centers": [round(float(c), 4) for c in best_centers],
            "shares": shares,
            "silhouette": best_s,
        },
    )
