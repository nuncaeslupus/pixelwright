import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage
from PIL import ImageFilter

from pixelwright.cli import main
from pixelwright.core.image import IndexedImage, RGBImage
from pixelwright.core.palette import Color, Palette
from pixelwright.core.quantize import quantize_fixed
from pixelwright.core.snap import snap
from pixelwright.fixtures.synth import Degradation, degrade, make_art, snap_cases
from pixelwright.io.png import write_png


def pixel_accuracy(truth: IndexedImage, snapped: RGBImage) -> float:
    """Share of truth pixels recovered, at the best alignment (a leading sliver cell may
    become its own cell, shifting the result by one)."""
    got, _ = quantize_fixed(snapped, truth.palette)
    best = 0.0
    for dy in (0, 1):
        for dx in (0, 1):
            g = got.indices[dy:, dx:]
            h, w = min(g.shape[0], truth.height), min(g.shape[1], truth.width)
            hits = int((g[:h, :w] == truth.indices[:h, :w]).sum())
            best = max(best, hits / truth.indices.size)
    return best


def test_snap_recovers_scale_on_synthetic_set() -> None:
    exact, accuracy = [], []
    for case in snap_cases(seed=0):
        result = snap(case.observed)
        exact.append(result.scale == case.degradation.scale)
        accuracy.append(pixel_accuracy(case.truth, result.image) if exact[-1] else 0.0)
    snap_scale_exact_rate = float(np.mean(exact))
    assert snap_scale_exact_rate >= 0.98
    assert float(np.mean(accuracy)) >= 0.97


def test_clean_upscale_is_recovered_exactly() -> None:
    rng = np.random.default_rng(4)
    art = make_art(rng, 24, 18)
    for scale in (2, 5, 8):
        result = snap(degrade(art, Degradation(scale=scale), rng))
        assert result.scale == scale
        assert pixel_accuracy(art, result.image) == 1.0
        assert result.confidence > 0.5


def test_given_scale_skips_detection() -> None:
    rng = np.random.default_rng(5)
    art = make_art(rng, 20, 16)
    result = snap(degrade(art, Degradation(scale=4, offset=(1, 3)), rng), scale=4)
    assert (result.scale, result.offset) == (4, (1, 3))
    with pytest.raises(ValueError):
        snap(result.image, scale=0)


def test_tiny_or_flat_images_fall_back_to_scale_one() -> None:
    flat = RGBImage.from_array(np.full((40, 40, 3), 90, dtype=np.uint8))
    assert snap(flat).scale == 1
    tiny = RGBImage.from_array(np.zeros((5, 5, 3), dtype=np.uint8))
    assert snap(tiny).scale == 1


def test_noisy_low_contrast_dither_keeps_the_large_scale() -> None:
    """A dithered gradient in close colors plus noise puts many peaks off the grid; chance
    normalization alone then prefers a divisor of the true scale (seen on real CC0 art)."""
    hits = 0
    for seed in range(30):
        rng = np.random.default_rng(seed)
        idx = np.arange(48)[None, :] // 2 + rng.integers(0, 2, (32, 48))
        pal = Palette([Color(40 + 4 * i, 30 + 4 * i, 80 + 4 * i) for i in range(idx.max() + 1)])
        art = IndexedImage.from_array(idx, pal)
        hits += snap(degrade(art, Degradation(12, (3, 5), noise=5.0), rng)).scale == 12
    assert hits >= 10


def test_blurred_art_on_an_even_subgrid_keeps_the_true_scale() -> None:
    """Art built mostly from 2x2 blocks (as on VGA screenshots) puts most borders on a
    grid of twice the scale too; after blur its coarse cells straddle the sparse 1-px
    details, so they are less uniform than the true scale's and must not win."""
    hits = 0
    for seed in range(60):
        rng = np.random.default_rng(seed)
        base = make_art(rng, 24, 18)
        idx = np.kron(base.indices, np.ones((2, 2), dtype=np.uint16))
        detail = rng.random(idx.shape) < 0.05
        idx[detail] = rng.integers(0, len(base.palette.colors), int(detail.sum()))
        art = IndexedImage.from_array(idx, base.palette)
        scale = int(rng.integers(5, 9))
        observed = degrade(art, Degradation(scale, (1, 2), blur=scale / 4), rng)
        hits += snap(observed).scale == scale
    assert hits >= 55


def test_normalize_warns_when_the_snapped_size_is_not_the_canvas(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path
    rng = np.random.default_rng(1)
    native = rng.integers(0, 255, (10, 12, 3), np.uint8)
    big = np.repeat(np.repeat(native, 4, 0), 4, 1)
    write_png(root / "src.png", RGBImage(np.dstack([big, np.full(big.shape[:2], 255, np.uint8)])))
    art = ["--workspace", str(root / "art"), "--json"]
    assert main(["init", *art]) == 0
    capsys.readouterr()
    assert main(["add", "props/box", "--from", str(root / "src.png"), *art]) == 0
    capsys.readouterr()
    assert main(["normalize", "props/box", *art]) == 0
    warnings = json.loads(capsys.readouterr().out)["warnings"]
    assert any("12x10" in w and "scale 4" in w and "320x180" in w for w in warnings), warnings


def test_a_painting_without_a_grid_is_reduced_to_the_canvas(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A smooth painting with a fine 2 px brush texture: snap finds that texture (640x360),
    far larger than the 320x180 canvas, so normalize reduces the whole image instead."""
    y, x = np.mgrid[0:720, 0:1280]
    smooth = np.stack(
        [100 * np.sin(x / 97), 100 * np.sin(y / 61 + x / 150), 100 * np.cos((x + y) / 83)], -1
    )
    texture = 12 * ((x // 2 + y // 2) % 2)[..., None]
    rgb = np.clip(128 + smooth + texture, 0, 255).astype(np.uint8)
    write_png(
        tmp_path / "paint.png", RGBImage(np.dstack([rgb, np.full((720, 1280), 255, np.uint8)]))
    )
    art = ["--workspace", str(tmp_path / "art"), "--json"]
    assert main(["init", *art]) == 0
    assert main(["add", "scenes/hill", "--from", str(tmp_path / "paint.png"), *art]) == 0
    capsys.readouterr()
    assert main(["normalize", "scenes/hill", *art]) == 0
    env = json.loads(capsys.readouterr().out)
    assert env["data"]["reduced"] and env["data"]["size"] == [320, 180]
    assert any("reduced 1280x720 to 320x180" in w for w in env["warnings"])


@pytest.mark.parametrize("factor", [8.6, 11.47])
def test_snap_recovers_non_integer_scale(factor: float) -> None:
    """Generators draw "pixels" 8.6 screen pixels wide; an integer grid would drift a
    cell every few cells and break dither and diagonals."""
    rng = np.random.default_rng(5)
    colors = np.array([(30, 20, 50), (200, 80, 60), (240, 200, 120), (40, 90, 60)], np.uint8)
    idx = rng.integers(0, 4, (30, 40))
    yy, xx = np.mgrid[0:30, 0:40]
    idx[:10] = np.where((yy[:10] + xx[:10]) % 2 == 0, 0, 1)  # dithered sky
    idx[np.abs(yy - xx + 5) < 1] = 2  # a 1:1 diagonal
    native = colors[idx]
    big = PILImage.fromarray(native).resize(
        (round(40 * factor), round(30 * factor)), PILImage.Resampling.NEAREST
    )
    big = big.filter(ImageFilter.GaussianBlur(0.6))
    rgba = np.dstack([np.asarray(big), np.full((big.height, big.width), 255, np.uint8)])
    result = snap(RGBImage(rgba))
    assert result.period[0] == pytest.approx(factor, abs=0.05)
    got = result.image.rgba[..., :3]
    assert got.shape[:2] == (30, 40)
    match = (np.abs(got.astype(int) - native.astype(int)).sum(axis=2) < 40).mean()
    assert match >= 0.95


def test_pixel_art_painted_larger_keeps_the_canvas_grid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A generator draws a 320x183 scene (mostly 2x2 blocks) as 1344x768 with soft 4.2 px
    cells: the grid found on its own is a multiple (7-8 px), half the detail; normalize
    must keep the canvas grid and stay close to the input."""
    rng = np.random.default_rng(0)
    colors = rng.integers(20, 235, (12, 3)).astype(np.uint8)
    idx = np.kron(rng.integers(0, 12, (92, 160)), np.ones((2, 2), int))[:183, :320]
    detail = rng.random(idx.shape) < 0.03
    idx[detail] = rng.integers(0, 12, int(detail.sum()))
    big = PILImage.fromarray(colors[idx]).resize((1344, 768), PILImage.Resampling.NEAREST)
    big = big.filter(ImageFilter.GaussianBlur(0.8))
    rgb = np.asarray(big)
    write_png(tmp_path / "t.png", RGBImage(np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)])))
    assert snap(RGBImage(np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)]))).image.width < 272
    art = ["--workspace", str(tmp_path / "art"), "--json"]
    assert main(["init", *art]) == 0
    assert main(["add", "rooms/tavern", "--from", str(tmp_path / "t.png"), *art]) == 0
    capsys.readouterr()
    assert main(["normalize", "rooms/tavern", *art]) == 0
    env = json.loads(capsys.readouterr().out)
    w, h = env["data"]["size"]
    assert abs(w / 320 - 1) <= 0.02 and abs(h / 180 - 1) <= 0.03 and not env["data"]["reduced"]
    with PILImage.open(env["outputs"][0]) as im:
        got = np.asarray(im.convert("RGB").resize((320, 183), PILImage.Resampling.NEAREST))
    match = (np.abs(got.astype(int) - colors[idx].astype(int)).sum(axis=2) < 60).mean()
    assert match >= 0.9
