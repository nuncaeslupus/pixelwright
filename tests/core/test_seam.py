"""Overlapping tiles meet along the seam where they agree, with no new colour."""

from __future__ import annotations

import numpy as np

from pixelwright.core.seam import join, seam_path

A, B, C = (200, 30, 30), (30, 200, 30), (30, 30, 200)


def test_seam_cut_follows_low_error() -> None:
    h, ov = 12, 8
    left = np.full((h, 20, 3), A, np.uint8)
    right = np.full((h, 20, 3), C, np.uint8)
    # in the overlap the tiles agree only along a diagonal band, column 2 + row // 3
    lo, ro = left[:, -ov:], right[:, :ov]
    lo[:] = A
    ro[:] = C
    for y in range(h):
        x = 2 + y // 3
        lo[y, x] = ro[y, x] = B
    path = seam_path(lo, ro)
    assert [int(p) for p in path] == [2 + y // 3 for y in range(h)]
    out = join(left, right, ov)
    assert out.shape == (h, 32, 3)
    assert {tuple(c) for c in out.reshape(-1, 3)} <= {A, B, C}
    assert (out[:, :12] == A).all() and (out[:, -12:] == C).all()


def test_join_without_overlap_concatenates() -> None:
    a = np.zeros((4, 3, 4), np.uint8)
    b = np.ones((4, 5, 4), np.uint8)
    assert join(a, b, 0).shape == (4, 8, 4)
