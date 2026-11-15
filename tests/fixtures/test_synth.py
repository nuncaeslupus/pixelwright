import hashlib
from pathlib import Path

import numpy as np
import pytest

from pixelwright.core.image import IndexedImage
from pixelwright.fixtures.cases import orphan_cases, read_case, write_case
from pixelwright.fixtures.synth import (
    DEFAULT_CASES,
    SCALES,
    Degradation,
    degrade,
    make_art,
    snap_cases,
)
from pixelwright.io.png import write_png


def _digest(seed: int, folder: Path) -> str:
    h = hashlib.sha256()
    for case in snap_cases(seed, count=30):
        write_png(folder / f"{case.id}-truth.png", case.truth)
        write_png(folder / f"{case.id}-observed.png", case.observed)
        h.update((folder / f"{case.id}-truth.png").read_bytes())
        h.update((folder / f"{case.id}-observed.png").read_bytes())
    return h.hexdigest()


def test_fixture_generator_is_deterministic(tmp_path: Path) -> None:
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    assert _digest(7, a) == _digest(7, b)
    assert _digest(7, a) != _digest(8, c)


def test_default_set_size_and_scale_coverage() -> None:
    cases = list(snap_cases(0))
    fixture_cases = len(cases) + len(list(orphan_cases(0)))
    assert fixture_cases >= 200
    assert len(cases) == DEFAULT_CASES
    assert {c.degradation.scale for c in cases} == set(SCALES)
    assert all(c.observed.width >= c.truth.width * c.degradation.scale for c in cases)


def test_clean_upscale_is_exact() -> None:
    rng = np.random.default_rng(0)
    art = make_art(rng, 10, 8)
    out = degrade(art, Degradation(scale=3), rng)
    np.testing.assert_array_equal(out.rgba[::3, ::3, :3], art.palette.rgb_array()[art.indices])


def test_offset_shifts_grid() -> None:
    rng = np.random.default_rng(1)
    art = make_art(rng, 6, 5)
    out = degrade(art, Degradation(scale=4, offset=(2, 1)), rng)
    assert (out.width, out.height) == (6 * 4 + 2, 5 * 4 + 1)
    with pytest.raises(ValueError):
        degrade(art, Degradation(scale=4, offset=(4, 0)), rng)


def test_detector_cases_roundtrip(tmp_path: Path) -> None:
    cases = list(orphan_cases(0, count=10))
    assert {c.expect for c in cases} == {"pass", "fail"}
    for case in cases:
        write_case(tmp_path / case.id, case)
        back = read_case(tmp_path / case.id)
        assert back == case
    failing = next(c for c in cases if c.expect == "fail")
    x, y, _, _ = failing.regions[0]
    assert isinstance(failing.image, IndexedImage)
    around = failing.image.indices[y - 1 : y + 2, x - 1 : x + 2].ravel().tolist()
    center = around.pop(4)
    assert center not in around
