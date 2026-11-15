import numpy as np

from pixelwright.core.checks import check_orphans
from pixelwright.core.checks.orphans import pair_mask
from pixelwright.core.image import IndexedImage
from pixelwright.core.palette import Color, Palette
from pixelwright.fixtures.cases import orphan_cases

PAL = Palette([Color(0, 0, 0), Color(255, 255, 255)])


def test_orphans_detector_meets_precision_recall() -> None:
    tp = fp = fn = 0
    region_hits = region_total = 0
    for seed in (0, 1, 2):
        for case in orphan_cases(seed, count=40):
            result = check_orphans(case.image)
            expected = case.expect == "fail"
            tp += result.flagged and expected
            fp += result.flagged and not expected
            fn += expected and not result.flagged
            found = {(x, y) for x, y, _, _ in result.regions}
            region_total += len(case.regions)
            region_hits += sum((x, y) in found for x, y, _, _ in case.regions)
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    assert precision >= 0.90
    assert recall >= 0.80
    assert region_hits == region_total  # every planted orphan is located


def test_single_and_pair_clusters() -> None:
    idx = np.zeros((6, 6), dtype=np.uint16)
    idx[1, 1] = 1  # orphan
    idx[4, 3] = idx[4, 4] = 1  # pair
    result = check_orphans(IndexedImage(idx, PAL))
    assert result.status == "warn"
    assert result.regions == ((1, 1, 1, 1),)
    assert result.details["pairs"] == 1
    assert pair_mask(IndexedImage(idx, PAL)).sum() == 2


def test_transparent_pixels_are_not_orphans() -> None:
    idx = np.zeros((3, 3), dtype=np.uint16)
    alpha = np.zeros((3, 3), dtype=bool)
    alpha[1, 1] = True  # one opaque pixel alone on transparency is an orphan
    assert check_orphans(IndexedImage(idx, PAL, alpha)).value == 1.0
    assert check_orphans(IndexedImage(idx, PAL)).status == "pass"
