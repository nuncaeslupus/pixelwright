import numpy as np
import pytest

from pixelwright.core.image import IndexedImage, RGBImage
from pixelwright.core.palette import Color, Palette
from pixelwright.core.quantize import quantize_fixed
from pixelwright.core.snap import snap
from pixelwright.fixtures.synth import Degradation, degrade, make_art, snap_cases


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
