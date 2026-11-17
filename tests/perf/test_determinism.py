"""Determinism and timing harness: run the fixture pipeline twice through the CLI."""

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from pixelwright.cli import main
from pixelwright.fixtures.synth import Degradation, degrade, make_art
from pixelwright.io.palette_io import write_palette
from pixelwright.io.png import write_png

STEPS = ("normalize", "check")
MAX_MS_PER_100K_PX = 2000


def _pw(capsys: pytest.CaptureFixture[str], *argv: str) -> dict[str, Any]:
    assert main([*argv, "--json"]) == 0
    env: dict[str, Any] = json.loads(capsys.readouterr().out)
    return env


def _pipeline(root: Path, capsys: pytest.CaptureFixture[str]) -> tuple[dict[str, str], list[int]]:
    """Return output hashes by step and each step's duration in ms."""
    art = root / "art"
    w = ["--workspace", str(art)]
    _pw(capsys, "init", *w)
    _pw(capsys, "palette", "import", "--file", str(root / "scene.gpl"), "--name", "main", *w)
    asset = art / "assets" / "scenes" / "bg"
    _pw(capsys, "add", "scenes/bg", "--from", str(root / "src.png"), *w)
    hashes, times = {}, []
    for step in STEPS:
        env = _pw(capsys, step, "scenes/bg", *w)
        version = asset / "versions" / f"{env['version']}.png"
        hashes[step] = hashlib.sha256(version.read_bytes()).hexdigest()
        times.append(env["duration_ms"])
    return hashes, times


@pytest.fixture
def source(tmp_path: Path) -> tuple[Path, int]:
    rng = np.random.default_rng(7)
    art = make_art(rng, 160, 90, n_colors=8)
    image = degrade(art, Degradation(scale=4, offset=(1, 2), blur=0.6), rng)
    write_png(tmp_path / "src.png", image)
    write_palette(tmp_path / "scene.gpl", art.palette)
    return tmp_path, image.width * image.height


def test_pipeline_rerun_is_byte_identical(
    source: tuple[Path, int], capsys: pytest.CaptureFixture[str]
) -> None:
    base, pixels = source
    runs = []
    for name in ("a", "b"):
        root = base / name
        root.mkdir()
        for f in ("src.png", "scene.gpl"):
            (root / f).write_bytes((base / f).read_bytes())
        runs.append(_pipeline(root, capsys))
    (first, t1), (second, t2) = runs
    assert first == second
    per_100k = np.array(t1 + t2) * 100_000 / pixels
    print(
        "ms per 100k px by step:",
        dict(zip(STEPS, per_100k[: len(STEPS)].round().tolist(), strict=True)),
    )
    assert float(np.percentile(per_100k, 95)) <= MAX_MS_PER_100K_PX
