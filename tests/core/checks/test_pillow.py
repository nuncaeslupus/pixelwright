import numpy as np
import numpy.typing as npt

from pixelwright.core.checks import check_pillow
from pixelwright.core.checks.shape import edge_distance
from pixelwright.core.image import IndexedImage
from pixelwright.core.palette import Color, Palette

RAMP = Palette(
    [Color(255, 0, 255)] + [Color(v, int(v * 0.8), int(v * 0.6)) for v in (40, 80, 120, 170, 220)]
)


def _shape(rng: np.random.Generator) -> npt.NDArray[np.bool_]:
    h, w = int(rng.integers(20, 40)), int(rng.integers(20, 40))
    yy, xx = np.mgrid[0:48, 0:48]
    kind = int(rng.integers(0, 3))
    if kind == 0:
        mask = ((yy - 24) / (h / 2)) ** 2 + ((xx - 24) / (w / 2)) ** 2 <= 1
    elif kind == 1:
        mask = (abs(yy - 24) < h / 2) & (abs(xx - 24) < w / 2)
    else:
        blob = ((yy - 20) / 12) ** 2 + ((xx - 20) / 14) ** 2 <= 1
        mask = blob | (((yy - 30) / 10) ** 2 + ((xx - 30) / 9) ** 2 <= 1)
    return np.asarray(mask, dtype=bool)


def _shade(mask: npt.NDArray[np.bool_], values: npt.NDArray[np.float64]) -> IndexedImage:
    v = values[mask]
    levels = np.clip(((v - v.min()) / max(np.ptp(v), 1e-9) * 4.999).astype(int), 0, 4) + 1
    idx = np.zeros(mask.shape, dtype=np.uint16)
    idx[mask] = levels
    return IndexedImage(idx, RAMP, mask)


def test_pillow_detector_flags_edge_driven_shading() -> None:
    rng = np.random.default_rng(0)
    tp = fp = fn = 0
    for i in range(60):
        mask = _shape(rng)
        yy, xx = np.mgrid[0 : mask.shape[0], 0 : mask.shape[1]]
        lx, ly = (float(v) for v in rng.uniform(-1, 1, 2))
        if i % 2:
            values = edge_distance(mask).astype(float)  # pillow: bright centre, dark rim
            expected = True
        else:
            values = xx * lx + yy * ly  # brighter toward the light
            expected = False
        flagged = check_pillow(_shade(mask, values), light=(lx, ly)).flagged
        tp += flagged and expected
        fp += flagged and not expected
        fn += expected and not flagged
    precision, recall = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    assert precision >= 0.90
    assert recall >= 0.80


def test_small_subject_passes() -> None:
    mask = np.zeros((10, 10), dtype=bool)
    mask[4:6, 4:6] = True
    assert check_pillow(_shade(mask, np.ones((10, 10)))).status == "pass"
