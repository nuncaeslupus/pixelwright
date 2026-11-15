"""Labelled detector cases: an image, the check it targets, the expected verdict, regions.

On disk a case is a folder: `image.png` (indexed) and `case.yaml`
(`pixelwright/case@1`: id, check, expect pass|fail, regions as [x, y, w, h] boxes, note).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from pixelwright.core.image import IndexedImage
from pixelwright.fixtures.synth import make_art
from pixelwright.io.png import read_png, write_png
from pixelwright.workspace import schema
from pixelwright.workspace.files import read_yaml, write_yaml

EXPECT = ("pass", "fail")
Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class DetectorCase:
    id: str
    check: str
    expect: str
    image: IndexedImage
    regions: tuple[Box, ...] = field(default_factory=tuple)
    note: str = ""

    def __post_init__(self) -> None:
        if self.expect not in EXPECT:
            raise ValueError(f"expect must be one of {EXPECT}")


def write_case(folder: Path, case: DetectorCase) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    write_png(folder / "image.png", case.image)
    data = {
        "id": case.id,
        "check": case.check,
        "expect": case.expect,
        "regions": [list(r) for r in case.regions],
        "note": case.note,
    }
    write_yaml(folder / "case.yaml", schema.stamp("case", data))


def read_case(folder: Path) -> DetectorCase:
    data = schema.validate("case", read_yaml(folder / "case.yaml"))
    image = read_png(folder / "image.png")
    if not isinstance(image, IndexedImage):
        raise ValueError(f"{folder}: case image must be an indexed PNG")
    regions = tuple((int(r[0]), int(r[1]), int(r[2]), int(r[3])) for r in data["regions"])
    return DetectorCase(
        data["id"], data["check"], data["expect"], image, regions, data.get("note", "")
    )


def remove_isolated(
    indices: np.ndarray[Any, np.dtype[np.uint16]],
) -> np.ndarray[Any, np.dtype[np.uint16]]:
    """Repaint every pixel with no same-colored 8-neighbour with its most common neighbour."""
    idx = indices.copy()
    h, w = idx.shape
    for y in range(h):
        for x in range(w):
            nb = idx[max(0, y - 1) : y + 2, max(0, x - 1) : x + 2].ravel().tolist()
            nb.remove(int(idx[y, x]))
            if nb and int(idx[y, x]) not in nb:
                idx[y, x] = max(set(nb), key=nb.count)
    return idx


def orphan_cases(seed: int = 0, count: int = 40) -> Iterator[DetectorCase]:
    """Half clean flat art (pass), half with planted isolated pixels (fail, boxes around them)."""
    for i in range(count):
        rng = np.random.default_rng(seed * 1_000_003 + 500_000 + i)
        raw = make_art(rng, int(rng.integers(20, 40)), int(rng.integers(16, 32)))
        art = IndexedImage(remove_isolated(raw.indices), raw.palette)
        if i % 2 == 0:
            yield DetectorCase(f"orphans-{seed}-{i:03d}", "orphans", "pass", art)
            continue
        idx = art.indices.copy()
        regions: list[Box] = []
        for _ in range(int(rng.integers(1, 4))):
            y, x = int(rng.integers(1, art.height - 1)), int(rng.integers(1, art.width - 1))
            around = idx[y - 1 : y + 2, x - 1 : x + 2]
            if len(np.unique(around)) != 1:
                continue  # only plant inside flat areas, so the pixel is a true orphan
            others = [c for c in range(len(art.palette)) if c != int(idx[y, x])]
            idx[y, x] = others[int(rng.integers(0, len(others)))]
            regions.append((x, y, 1, 1))
        if not regions:
            yield DetectorCase(f"orphans-{seed}-{i:03d}", "orphans", "pass", art)
            continue
        image = IndexedImage(idx, art.palette)
        yield DetectorCase(f"orphans-{seed}-{i:03d}", "orphans", "fail", image, tuple(regions))
