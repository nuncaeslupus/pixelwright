"""`pw regen-region` with the offline replay provider."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from pixelwright.cli import main
from pixelwright.core.image import RGBImage
from pixelwright.fixtures import tour
from pixelwright.io.png import encode_png, read_png
from pixelwright.workspace import Workspace


def _pw(ws: Path, capsys: pytest.CaptureFixture[str], *args: str) -> dict[str, Any]:
    code = main([*args, "--workspace", str(ws), "--json"])
    out: dict[str, Any] = json.loads(capsys.readouterr().out)
    out["exit"] = code
    return out


def test_regen_region_changes_nothing_outside_mask(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws = tmp_path / "ws"
    _pw(ws, capsys, "init", "--legacy")
    (ws / "replay").mkdir()
    noise = np.random.default_rng(7).integers(0, 256, (360, 640, 3), dtype=np.uint8)
    (ws / "replay" / "noise.png").write_bytes(encode_png(RGBImage.from_array(noise)))
    src = tmp_path / "scene.png"
    src.write_bytes(encode_png(tour.scene()))
    _pw(ws, capsys, "new", "hill", "--kind", "background", "--canvas", "160x90")
    _pw(ws, capsys, "attach", "hill", str(src))
    _pw(ws, capsys, "issue", "hill", "add", "--box", "10,20,30,15", "--note", "busier sky")

    out = _pw(ws, capsys, "regen-region", "hill", "--issue", "issue-1", "--provider", "replay")
    assert out["exit"] == 0 and out["version"] == "v0002", out
    asset = Workspace.open(ws).asset("hill")
    before = read_png(asset.versions_dir / "v0001" / "image.png").to_rgba()
    after = read_png(asset.versions_dir / "v0002" / "image.png").to_rgba()
    inside = np.zeros(before.shape[:2], dtype=bool)
    inside[20:35, 10:40] = True
    assert (after[~inside] == before[~inside]).all()  # pixels_changed_outside_mask == 0
    assert out["data"]["changed"] > 0 and (after[inside] != before[inside]).any()
    meta = asset.meta("v0002")
    assert meta["step"] == "regen-region" and meta["parent"] == "v0001"
    assert asset.issue("issue-1")["status"] == "fixed"
