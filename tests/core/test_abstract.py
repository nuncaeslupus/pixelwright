"""Paintings to readable pixels: flatten texture, fold specks, keep accents."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage

from pixelwright.cli import main
from pixelwright.core.abstract import kuwahara, remove_small_clusters, small_cluster_share
from pixelwright.core.image import IndexedImage, RGBImage
from pixelwright.core.palette import Color, Palette
from pixelwright.core.quantize import quantize_fixed
from pixelwright.io.png import write_png


def _textured_painting() -> np.ndarray:
    """1280x720: dusk sky, a hill of noisy brush texture, a lit window on a dark house."""
    rng = np.random.default_rng(6)
    y, x = np.mgrid[0:720, 0:1280]
    rgb = np.zeros((720, 1280, 3))
    rgb[...] = np.stack([90 + y / 6, 70 + y / 10, 140 - y / 10], -1)  # sky
    hill = y > 360 + 80 * np.sin(x / 300)
    rgb[hill] = (90, 75, 45)
    rgb[hill] += rng.normal(0, 28, (int(hill.sum()), 3))  # brush texture
    rgb[300:420, 700:900] = (45, 35, 40)  # house
    rgb[340:370, 760:800] = (255, 190, 60)  # lit window
    return np.clip(rgb, 0, 255).astype(np.uint8)


def test_kuwahara_flattens_noise_and_keeps_edges() -> None:
    rng = np.random.default_rng(1)
    a = np.zeros((40, 40, 3))
    a[:, 20:] = 200
    a += rng.normal(0, 20, a.shape)
    out = kuwahara(a, 3)
    assert out[:, 3:17].std() < a[:, 3:17].std() / 2
    assert out[:, 18].mean() < 60 and out[:, 21].mean() > 140  # the edge stays sharp


def test_small_clusters_fold_unless_protected() -> None:
    palette = Palette([Color(0, 0, 0), Color(255, 255, 255)])
    idx = np.zeros((10, 10), np.uint16)
    idx[2, 2] = idx[2, 3] = 1  # a 2-px speck
    idx[7, 7] = 1  # a protected star
    image = IndexedImage(idx, palette)
    protect = np.zeros((10, 10), bool)
    protect[7, 7] = True
    out, changed = remove_small_clusters(image, protect=protect)
    assert changed == 2 and out.indices[2, 2] == 0 and out.indices[7, 7] == 1


def test_painting_regions_are_flat(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_png(tmp_path / "paint.png", RGBImage.from_array(_textured_painting()))
    art = ["--workspace", str(tmp_path / "art"), "--json"]
    assert main(["init", *art]) == 0
    assert main(["add", "scenes/hill", "--from", str(tmp_path / "paint.png"), *art]) == 0
    capsys.readouterr()
    assert main(["normalize", "scenes/hill", *art]) == 0
    env = json.loads(capsys.readouterr().out)
    assert env["data"]["reduced"]
    version = tmp_path / "art" / "assets" / "scenes" / "hill" / "versions" / "v001.png"
    rgba = np.asarray(PILImage.open(version).convert("RGBA")).copy()
    image = RGBImage(rgba)
    colours = sorted({tuple(c) for c in rgba[..., :3].reshape(-1, 3).tolist()})
    indexed, _ = quantize_fixed(image, Palette([Color(*c) for c in colours]))
    assert small_cluster_share(indexed) <= 0.02
    window = rgba[85:92, 190:200, :3].astype(int)  # 340-370 x 760-800 at a quarter
    assert (window[..., 0] > 200).any() and (window[..., 1] > 140).any()
