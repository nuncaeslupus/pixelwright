"""Sprites drawn on a flat background: key it out and frame the figure.

Image models cannot paint transparency, so a sprite prompt asks for a flat background
(magenta, green). `key_background` finds that colour on the border and makes it
transparent wherever it reaches from the edge (and in enclosed gaps, with a tighter
tolerance), so it never enters the palette. `frame` crops to the figure plus a margin and
pads it to the canvas shape, so reducing to the canvas keeps the figure as large as it
can be. `outline_reduce` scales down keeping thin dark outlines that an area average
would wash out.
"""

from __future__ import annotations

from collections import deque

import numpy as np
import numpy.typing as npt

from pixelwright.core.color import srgb8_to_oklab
from pixelwright.core.image import RGBImage

BAND = 4  # border band (px) where the background colour is measured
COVER = 0.95  # share of that band the background must cover
KEY_DE = 0.12  # OKLab distance keyed from the edge (noise, soft anti-aliased fringe)
HOLE_DE = 0.06  # tighter, for enclosed gaps (between an arm and the body)
MIN_KEYED = 0.2  # a keyed area smaller than this share of the image is no background
MAX_KEYED = 0.98  # ... and one larger leaves no figure (a flat image)
MARGIN = 0.04  # margin around the figure, as a share of its larger side
OUTLINE = 0.3  # share of a block that dark outline pixels must cover to be kept

Bool = npt.NDArray[np.bool_]


def _band(a: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    return np.concatenate(
        [a[:BAND].reshape(-1, 3), a[-BAND:].reshape(-1, 3),
         a[:, :BAND].reshape(-1, 3), a[:, -BAND:].reshape(-1, 3)]
    )  # fmt: skip


def background(image: RGBImage) -> tuple[int, int, int] | None:
    """The flat colour around the figure, or None when the border is not one colour (a
    scene) or already transparent."""
    rgba = image.rgba
    if (rgba[..., 3] < 255).any():
        return None
    lab = srgb8_to_oklab(rgba[..., :3])
    band = _band(lab)
    centre = np.median(band, axis=0)
    if (np.linalg.norm(band - centre, axis=1) <= KEY_DE).mean() < COVER:
        return None
    rgb = _band(rgba[..., :3].astype(np.float64))
    near = np.linalg.norm(band - centre, axis=1) <= KEY_DE
    r, g, b = np.median(rgb[near], axis=0).round().astype(int)
    return int(r), int(g), int(b)


def key_background(image: RGBImage, colour: tuple[int, int, int]) -> RGBImage | None:
    """The image with `colour` made transparent where it touches the edge (flood fill)
    and in enclosed gaps; None when too little of the image is that colour."""
    rgba = image.rgba.copy()
    lab = srgb8_to_oklab(rgba[..., :3])
    dist = np.linalg.norm(lab - srgb8_to_oklab(np.array([colour], np.uint8))[0], axis=-1)
    near = dist <= KEY_DE
    h, w = near.shape
    keyed = np.zeros((h, w), bool)
    queue: deque[tuple[int, int]] = deque()
    for y, x in [(y, x) for y in range(h) for x in (0, w - 1)] + [
        (y, x) for x in range(w) for y in (0, h - 1)
    ]:
        if near[y, x] and not keyed[y, x]:
            keyed[y, x] = True
            queue.append((y, x))
    while queue:
        y, x = queue.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and near[ny, nx] and not keyed[ny, nx]:
                keyed[ny, nx] = True
                queue.append((ny, nx))
    keyed |= dist <= HOLE_DE
    if not MIN_KEYED <= keyed.mean() <= MAX_KEYED:
        return None
    rgba[keyed, 3] = 0
    return RGBImage(rgba)


def frame(image: RGBImage, canvas: tuple[int, int]) -> RGBImage:
    """Crop to the opaque figure plus a margin, padded with transparency to the canvas
    aspect ratio and centred (feet stay at the bottom margin)."""
    opaque = image.rgba[..., 3] >= 128
    if not opaque.any():
        return image
    ys, xs = np.nonzero(opaque)
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    m = round(MARGIN * max(y1 - y0, x1 - x0))
    fig_h, fig_w = y1 - y0 + 2 * m, x1 - x0 + 2 * m
    aspect = canvas[0] / canvas[1]
    out_w, out_h = max(fig_w, round(fig_h * aspect)), max(fig_h, round(fig_w / aspect))
    out = np.zeros((out_h, out_w, 4), np.uint8)
    oy, ox = out_h - fig_h + m, (out_w - (x1 - x0)) // 2
    out[oy : oy + y1 - y0, ox : ox + x1 - x0] = image.rgba[y0:y1, x0:x1]
    return RGBImage(out)


def outline_reduce(image: RGBImage, canvas: tuple[int, int]) -> RGBImage:
    """Area-average down to the canvas, but a block where dark outline pixels cover at
    least OUTLINE of the opaque area takes the outline's colour, so 1-px outlines
    survive; transparency is decided per block by majority."""
    rgba = image.rgba.astype(np.float64)
    h, w = rgba.shape[:2]
    cw, ch = canvas
    lum = srgb8_to_oklab(image.rgba[..., :3])[..., 0]
    opaque = image.rgba[..., 3] >= 128
    dark = opaque & (lum <= np.percentile(lum[opaque], 15)) if opaque.any() else opaque
    out = np.zeros((ch, cw, 4), np.uint8)
    ys = np.linspace(0, h, ch + 1).round().astype(int)
    xs = np.linspace(0, w, cw + 1).round().astype(int)
    for i in range(ch):
        for j in range(cw):
            sl = (slice(ys[i], ys[i + 1]), slice(xs[j], xs[j + 1]))
            block_opaque = opaque[sl]
            if not block_opaque.size or block_opaque.mean() < 0.5:
                continue
            block = rgba[sl][block_opaque][:, :3]
            block_dark = dark[sl][block_opaque]
            pick = block[block_dark] if block_dark.mean() >= OUTLINE else block
            out[i, j, :3] = np.clip(pick.mean(axis=0).round(), 0, 255)
            out[i, j, 3] = 255
    return RGBImage(out)
