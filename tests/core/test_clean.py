import numpy as np

from pixelwright.core.checks.orphans import orphan_mask
from pixelwright.core.clean import clean
from pixelwright.core.image import IndexedImage
from pixelwright.core.palette import Color, Palette
from pixelwright.fixtures.cases import orphan_cases

PAL = Palette([Color(0, 0, 0), Color(255, 255, 255), Color(250, 250, 250)])


def test_clean_removes_orphans_only_inside_mask() -> None:
    orphans_after_clean = 0
    for case in orphan_cases(0, count=40):
        if case.expect != "fail":
            continue
        image = case.image
        mask = np.zeros(image.indices.shape, dtype=bool)
        mask[:, : image.width // 2] = True
        out, report = clean(image, mask)
        orphans_after_clean += report.orphans_after
        np.testing.assert_array_equal(out.indices[~mask], image.indices[~mask])
        assert not (orphan_mask(out) & mask).any()
        # Orphans outside the mask stay where they were.
        assert (orphan_mask(out) & ~mask).sum() == (orphan_mask(image) & ~mask).sum()
    assert orphans_after_clean == 0


def test_clean_everywhere_and_tie_break_by_color() -> None:
    idx = np.zeros((5, 6), dtype=np.uint16)
    idx[:, 3:] = 1
    idx[2, 2] = 2  # near-white orphan on the boundary: 3 white vs 5 black neighbours
    out, report = clean(IndexedImage(idx, PAL))
    assert out.indices[2, 2] == 0 and report.changed == 1 and report.orphans_after == 0


def test_pairs_and_transparency() -> None:
    idx = np.zeros((6, 6), dtype=np.uint16)
    idx[2, 2] = idx[2, 3] = 1
    out, report = clean(IndexedImage(idx, PAL), pairs=True)
    assert (out.indices == 0).all() and report.pairs_removed == 2
    alpha = np.zeros((3, 3), dtype=bool)
    alpha[1, 1] = True
    lone, _ = clean(IndexedImage(np.zeros((3, 3), dtype=np.uint16), PAL, alpha))
    assert not lone.opaque().any()  # an opaque speck on transparency becomes transparent
