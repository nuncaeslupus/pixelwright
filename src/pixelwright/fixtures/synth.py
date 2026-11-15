"""Deterministic synthetic fixtures.

`make_art` paints small true pixel art (indexed). `degrade` turns it into the kind of
pseudo-pixel image an image model returns: integer upscale with a grid offset, sub-cell
jitter of cell borders, blur, JPEG and noise. A `SnapCase` keeps the truth next to it,
so snap and quantize can be scored exactly. Same seed, same bytes.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image as PILImage

from pixelwright.core.image import IndexedImage, RGBImage
from pixelwright.core.palette import Color, Palette

DEFAULT_CASES = 240
SCALES = tuple(range(2, 13))


def random_palette(rng: np.random.Generator, n: int) -> Palette:
    """`n` distinct, well separated colors (min 48 levels apart on some channel)."""
    colors: list[tuple[int, int, int]] = []
    while len(colors) < n:
        c = tuple(int(v) for v in rng.integers(0, 256, 3))
        if all(max(abs(a - b) for a, b in zip(c, o, strict=True)) >= 48 for o in colors):
            colors.append((c[0], c[1], c[2]))
    return Palette([Color(*c) for c in colors])


def make_art(rng: np.random.Generator, width: int, height: int, n_colors: int = 6) -> IndexedImage:
    """Flat shapes (rectangles, discs, lines) on a background, no isolated pixels by design."""
    palette = random_palette(rng, n_colors)
    idx = np.zeros((height, width), dtype=np.uint16)
    ys, xs = np.mgrid[0:height, 0:width]
    for _ in range(int(rng.integers(3, 8))):
        color = int(rng.integers(1, n_colors))
        kind = int(rng.integers(0, 3))
        cx, cy = int(rng.integers(0, width)), int(rng.integers(0, height))
        if kind == 0:
            w, h = (
                int(rng.integers(3, max(4, width // 2))),
                int(rng.integers(3, max(4, height // 2))),
            )
            idx[cy : cy + h, cx : cx + w] = color
        elif kind == 1:
            r = int(rng.integers(2, max(3, min(width, height) // 3)))
            idx[(xs - cx) ** 2 + (ys - cy) ** 2 <= r * r] = color
        else:
            thick = int(rng.integers(2, 4))
            if rng.random() < 0.5:
                idx[cy : cy + thick, :] = color
            else:
                idx[:, cx : cx + thick] = color
    return IndexedImage(idx, palette)


def _blur(
    img: np.ndarray[Any, np.dtype[np.float64]], sigma: float
) -> np.ndarray[Any, np.dtype[np.float64]]:
    if sigma <= 0:
        return img
    radius = max(1, int(3 * sigma))
    x = np.arange(-radius, radius + 1, dtype=np.float64)
    k = np.exp(-(x * x) / (2 * sigma * sigma))
    k /= k.sum()
    pad = np.pad(img, ((radius, radius), (radius, radius), (0, 0)), mode="edge")
    tmp = sum(k[i] * pad[:, i : i + img.shape[1], :] for i in range(len(k)))
    return sum(k[i] * tmp[i : i + img.shape[0], :, :] for i in range(len(k)))  # type: ignore[no-any-return]


def _cell_edges(
    n: int, scale: int, offset: int, jitter: float, rng: np.random.Generator
) -> np.ndarray[Any, np.dtype[np.int64]]:
    """Output pixel -> source cell along one axis; borders jittered by up to `jitter` cells."""
    borders = offset + scale * np.arange(n + 1, dtype=np.float64)
    if jitter > 0:
        borders[1:-1] += rng.uniform(-jitter, jitter, n - 1) * scale
    total = offset + scale * n
    pos = np.arange(total) + 0.5
    cells = np.searchsorted(borders, pos, side="right") - 1
    return np.clip(cells, 0, n - 1).astype(np.int64)


@dataclass(frozen=True)
class Degradation:
    scale: int
    offset: tuple[int, int] = (0, 0)  # (x, y) in output pixels, < scale
    jitter: float = 0.0  # max border shift, fraction of a cell
    blur: float = 0.0  # gaussian sigma in output pixels
    jpeg: int = 0  # JPEG quality, 0 = none
    noise: float = 0.0  # gaussian noise sigma, 0-255 scale


def degrade(art: IndexedImage, d: Degradation, rng: np.random.Generator) -> RGBImage:
    if not 0 <= d.offset[0] < d.scale or not 0 <= d.offset[1] < d.scale:
        raise ValueError("offset must be in [0, scale)")
    rgb = art.palette.rgb_array()[art.indices]
    rows = _cell_edges(art.height, d.scale, d.offset[1], d.jitter, rng)
    cols = _cell_edges(art.width, d.scale, d.offset[0], d.jitter, rng)
    big = rgb[rows][:, cols].astype(np.float64)
    big = _blur(big, d.blur)
    if d.noise > 0:
        big = big + rng.normal(0.0, d.noise, big.shape)
    out = np.clip(np.rint(big), 0, 255).astype(np.uint8)
    if d.jpeg:
        buf = io.BytesIO()
        PILImage.fromarray(out, mode="RGB").save(buf, format="JPEG", quality=d.jpeg)
        buf.seek(0)
        with PILImage.open(buf) as im:
            out = np.asarray(im.convert("RGB"), dtype=np.uint8).copy()
    return RGBImage.from_array(out)


@dataclass(frozen=True)
class SnapCase:
    id: str
    seed: int
    truth: IndexedImage
    observed: RGBImage
    degradation: Degradation
    tags: tuple[str, ...] = field(default_factory=tuple)


def _degradation(rng: np.random.Generator, scale: int) -> tuple[Degradation, tuple[str, ...]]:
    tags = [f"x{scale}"]
    offset = (int(rng.integers(0, scale)), int(rng.integers(0, scale)))
    jitter = float(rng.choice([0.0, 0.05, 0.1]))
    blur = float(rng.choice([0.0, 0.0, 0.5, 1.0])) * (scale / 4)
    jpeg = int(rng.choice([0, 0, 85, 70]))
    noise = float(rng.choice([0.0, 2.0, 5.0]))
    for name, on in (
        ("offset", offset != (0, 0)),
        ("jitter", jitter),
        ("blur", blur),
        ("jpeg", jpeg),
        ("noise", noise),
    ):
        if on:
            tags.append(name)
    return Degradation(scale, offset, jitter, blur, jpeg, noise), tuple(tags)


def snap_cases(seed: int = 0, count: int = DEFAULT_CASES) -> Iterator[SnapCase]:
    """`count` cases cycling through scales 2-12, each with its own child seed."""
    for i in range(count):
        case_seed = seed * 1_000_003 + i
        rng = np.random.default_rng(case_seed)
        scale = SCALES[i % len(SCALES)]
        w, h = int(rng.integers(16, 48)), int(rng.integers(12, 36))
        art = make_art(rng, w, h, n_colors=int(rng.integers(3, 9)))
        d, tags = _degradation(rng, scale)
        yield SnapCase(f"snap-{seed}-{i:04d}", case_seed, art, degrade(art, d, rng), d, tags)
