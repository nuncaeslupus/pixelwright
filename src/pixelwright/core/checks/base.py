"""Common check result, region helpers and the `report.json` writer."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from pixelwright.workspace import schema
from pixelwright.workspace.files import write_bytes_atomic

STATUSES = ("pass", "warn", "fail")
Box = tuple[int, int, int, int]  # x, y, w, h in native pixels


@dataclass(frozen=True)
class CheckResult:
    check: str
    rule: str
    status: str
    value: float
    threshold: float | None = None
    regions: tuple[Box, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")

    @property
    def flagged(self) -> bool:
        return self.status != "pass"

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check,
            "rule": self.rule,
            "status": self.status,
            "value": self.value,
            "threshold": self.threshold,
            "regions": [{"box": list(b)} for b in self.regions],
            "details": self.details,
        }


def tile_boxes(mask: npt.NDArray[np.bool_], tile: int = 16) -> tuple[Box, ...]:
    """Boxes of the `tile` x `tile` tiles that contain any True pixel (clipped to the image)."""
    h, w = mask.shape
    boxes = []
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            if mask[y : y + tile, x : x + tile].any():
                boxes.append((x, y, min(tile, w - x), min(tile, h - y)))
    return tuple(boxes)


def pixel_boxes(mask: npt.NDArray[np.bool_], limit: int = 200) -> tuple[Box, ...]:
    ys, xs = np.nonzero(mask)
    return tuple((int(x), int(y), 1, 1) for y, x in list(zip(ys, xs, strict=True))[:limit])


def write_report(path: Path, results: Sequence[CheckResult] | Iterable[CheckResult]) -> None:
    data = schema.stamp("report", {"results": [r.to_dict() for r in results]})
    write_bytes_atomic(path, (json.dumps(data, indent=2) + "\n").encode("utf-8"))


def read_report(path: Path) -> list[dict[str, Any]]:
    data = schema.validate("report", json.loads(path.read_text(encoding="utf-8")))
    return list(data["results"])
