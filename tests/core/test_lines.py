"""Jaggy 1-px lines become clean pixel-art steps."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from pixelwright.core.checks.line_runs import (
    _runs,
    check_line_runs,
    line_components,
    runs_are_clean,
)
from pixelwright.core.image import IndexedImage
from pixelwright.core.lines import clean_runs, regularise_lines
from pixelwright.core.palette import Color, Palette

PALETTE = Palette([Color(40, 30, 60), Color(10, 10, 10), Color(200, 120, 80)])


def _roof() -> IndexedImage:
    """A dark roof line over a wall, stepping 1,2,1,3,1,2,1 (jaggy)."""
    idx = np.zeros((20, 30), np.uint16)
    idx[12:, :] = 2  # wall below
    x, y = 2, 10
    for run in (1, 2, 1, 3, 1, 2, 1):
        idx[y, x : x + run] = 1
        x, y = x + run, y - 1
    return IndexedImage(idx, PALETTE)


def test_clean_runs_patterns() -> None:
    assert clean_runs(9, 3) == [3, 3, 3]
    assert clean_runs(9, 6) == [2, 1, 2, 1, 2, 1]
    assert sum(clean_runs(11, 7)) == 11


def test_diagonals_regularised() -> None:
    image = _roof()
    assert check_line_runs(image).status == "warn"
    fixed, count = regularise_lines(image)
    assert count == 1
    assert check_line_runs(fixed).status == "pass"
    (line,) = line_components(fixed)
    assert runs_are_clean(_runs(line))
    assert (fixed.indices[12:] == 2).all()  # the wall is untouched


def test_curves_are_left_alone() -> None:
    idx = np.zeros((20, 30), np.uint16)
    for x in range(2, 28):  # an arc: far from its chord
        idx[int(15 - 10 * np.sin(np.pi * (x - 2) / 25)), x] = 1
    image = IndexedImage(idx, PALETTE)
    _, count = regularise_lines(image)
    assert count == 0


def test_check_proposes_the_regularised_line(tmp_path: Path) -> None:
    """`pw check` flags the jaggy roof (R-PIX-4) and the scripts propose the fix."""
    from PIL import Image

    from pixelwright.asset import Asset
    from pixelwright.cli import main
    from pixelwright.flow import run_checks
    from pixelwright.issues import IssueLog
    from pixelwright.project import load_project

    art = tmp_path / "art"
    assert main(["init", "--workspace", str(art)]) == 0
    asset = Asset.create(load_project(art), "props/roof")
    asset.add_version(Image.fromarray(_roof().to_rgba(), "RGBA"))
    _, issues = run_checks(asset)
    jaggy = [i for i in issues if i.rule == "R-PIX-4"]
    assert jaggy
    fixes = IssueLog(asset).state().fixes.values()
    assert any(f.by == "script" and f.issue == jaggy[0].id for f in fixes)
