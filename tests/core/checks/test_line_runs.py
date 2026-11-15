import numpy as np

from pixelwright.core.checks import check_banding, check_line_runs
from pixelwright.core.checks.line_runs import runs_are_clean
from pixelwright.core.image import IndexedImage
from pixelwright.core.palette import Color, Palette

PAL = Palette([Color(20, 20, 30), Color(240, 230, 200), Color(110, 100, 120), Color(200, 60, 60)])


def _line(runs: list[int], l_corner: bool = False, transpose: bool = False) -> IndexedImage:
    idx = np.ones((40, 60), dtype=np.uint16)  # light background
    x, y = 2, 2
    for i, r in enumerate(runs):
        idx[y, x : x + r] = 0
        x += r
        if l_corner and i == len(runs) // 2:
            idx[y + 1, x - 1] = 0  # doubled corner below the run end
        y += 1
    if transpose:
        idx = np.ascontiguousarray(idx.T)
    return IndexedImage(idx, PAL)


def test_line_runs_flags_broken_run_sequences() -> None:
    assert check_line_runs(_line([2, 1, 3, 1, 2, 1, 3])).flagged
    assert not check_line_runs(_line([1, 1, 2, 2, 3, 3, 4])).flagged
    assert not runs_are_clean([3, 2, 1, 3, 1, 2])
    assert not runs_are_clean([1, 2, 1, 3, 1, 2])
    assert runs_are_clean([1, 1, 2, 2, 3])
    assert runs_are_clean([2, 1, 2, 1, 2, 1])


def test_line_runs_recall_and_precision_on_synthetic_lines() -> None:
    rng = np.random.default_rng(0)
    tp = fp = fn = 0
    for i in range(120):
        n = int(rng.integers(6, 10))
        kind = i % 4
        if kind == 0:
            runs = sorted(int(v) for v in rng.integers(1, 5, n))
        elif kind == 1:
            a, b = (int(v) for v in rng.integers(1, 4, 2))
            runs = [a, b] * (n // 2)
        else:
            runs = [int(v) for v in rng.integers(1, 5, n)]
            while runs_are_clean(runs):
                runs = [int(v) for v in rng.integers(1, 5, n)]
        corner = kind == 3
        if corner:
            runs = sorted(runs)
        image = _line(runs, l_corner=corner, transpose=bool(i % 2))
        expected = kind >= 2
        flagged = check_line_runs(image).flagged
        tp += flagged and expected
        fp += flagged and not expected
        fn += expected and not flagged
    recall, precision = tp / (tp + fn), tp / max(tp + fp, 1)
    assert recall >= 0.80
    assert precision >= 0.90


def test_l_corner_is_counted() -> None:
    result = check_line_runs(_line([1, 1, 2, 2, 3, 3], l_corner=True))
    assert result.details["l_corner_pixels"] >= 1


def _rings(width: int) -> IndexedImage:
    yy, xx = np.mgrid[0:48, 0:48]
    r = np.hypot(yy - 24, xx - 24)
    idx = np.zeros((48, 48), dtype=np.uint16)  # dark outside
    idx[r < 18 + width] = 2  # mid ring
    idx[r < 18] = 1  # light core
    return IndexedImage(idx, PAL)


def test_banding_flags_thin_contour_bands_only() -> None:
    assert check_banding(_rings(1)).flagged
    assert not check_banding(_rings(5)).flagged
    flat = IndexedImage(np.zeros((10, 10), dtype=np.uint16), PAL)
    assert check_banding(flat).status == "pass"
