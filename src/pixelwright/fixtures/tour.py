"""The tour's sample, drawn by code (D-M3-4): a hillside house at dusk.

`scene()` is the native 160x90 truth; `sketch()` is the artist's line drawing at 4x;
`painted()` is what an image model might return for it: the scene at 4x with soft edges,
noise and a slightly uneven grid, so snap, quantize and clean all have work to do.
"""

from __future__ import annotations

import numpy as np

from pixelwright.core.image import IndexedImage, RGBImage
from pixelwright.core.palette import Color, Palette
from pixelwright.fixtures.synth import Degradation, degrade

WIDTH, HEIGHT, SCALE = 160, 90, 4
SEED = 1990

PALETTE_HEX = (
    "#2b2340",  # 0 night sky
    "#4a3a66",  # 1 upper sky
    "#8a5a7a",  # 2 dusk band
    "#e09a6a",  # 3 horizon glow
    "#f4d58a",  # 4 sun, lit window
    "#3a4a5a",  # 5 far hills
    "#2f5a3a",  # 6 hill
    "#1f3a2a",  # 7 hill shadow, tree
    "#c8b08a",  # 8 wall
    "#8a3a2a",  # 9 roof
    "#3a2a24",  # 10 door, outline
    "#5a7a4a",  # 11 grass light
)


def palette() -> Palette:
    return Palette([Color.from_hex(h) for h in PALETTE_HEX], name="tour")


def scene() -> IndexedImage:
    ys, xs = np.mgrid[0:HEIGHT, 0:WIDTH]
    idx = np.zeros((HEIGHT, WIDTH), dtype=np.uint16)
    idx[ys >= 14] = 1
    idx[ys >= 30] = 2
    idx[ys >= 44] = 3
    idx[(xs - 118) ** 2 + (ys - 46) ** 2 <= 49] = 4  # sun on the horizon
    far = 50 + 6 * np.sin(xs / 13.0) + 3 * np.sin(xs / 5.0 + 1)
    idx[ys >= far] = 5
    hill = 58 + 10 * np.cos((xs - 50) / 40.0)
    idx[ys >= hill] = 6
    idx[(ys >= hill) & (xs > 95 + (ys - 58) * 2)] = 7  # shadow side
    idx[(ys >= hill + 6) & (xs < 70) & ((xs * 7 + ys * 13) % 23 == 0)] = 11  # grass tufts
    # house
    idx[50:64, 36:58] = 8
    for row in range(10):
        idx[40 + row, 36 + 10 - row : 58 - 10 + row + 1] = 9
    idx[56:64, 44:49] = 10
    idx[53:57, 51:55] = 4
    # tree
    idx[(xs - 76) ** 2 + ((ys - 48) * 1.3) ** 2 <= 64] = 7
    idx[54:64, 75:78] = 10
    return IndexedImage(idx, palette())


def sketch() -> RGBImage:
    """Dark lines on paper where major shapes meet, at 4x, as a scanned pencil drawing."""
    idx = scene().indices.astype(np.int32)
    groups = np.array([0, 0, 0, 0, 1, 2, 3, 3, 4, 5, 6, 3])  # sky bands are one shape
    g = groups[idx]
    edge = np.zeros_like(g, dtype=bool)
    edge[:, 1:] |= g[:, 1:] != g[:, :-1]
    edge[1:, :] |= g[1:, :] != g[:-1, :]
    big = np.kron(edge, np.ones((SCALE, SCALE), dtype=bool))
    paper = np.full((*big.shape, 3), (238, 233, 222), dtype=np.uint8)
    paper[big] = (70, 64, 60)
    rng = np.random.default_rng(SEED)
    noisy = paper.astype(np.int16) + rng.integers(-6, 7, paper.shape[:2])[..., None]
    return RGBImage.from_array(np.clip(noisy, 0, 255).astype(np.uint8))


def painted() -> RGBImage:
    d = Degradation(scale=SCALE, offset=(1, 2), jitter=0.08, blur=0.9, noise=5.0)
    img = degrade(scene(), d, np.random.default_rng(SEED))
    return RGBImage(np.ascontiguousarray(img.rgba[: HEIGHT * SCALE, : WIDTH * SCALE]))
