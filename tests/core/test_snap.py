import numpy as np
import pytest

from pixelwright.core.image import IndexedImage, RGBImage
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
