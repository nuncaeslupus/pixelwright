"""Engine-ready pieces of a lit scene: light masks, flicker curves, procedural flames, palette snap.

A scene for an engine is a static background (static light painted in) plus separate moving
parts: sprite strips with their own loop, one light mask per light and the curve that
drives it. Every moving colour comes from the scene's own palette, and every previewed
frame is snapped back to it, because a light that multiplies colours leaves the palette
otherwise. Guide: `docs/guide/scene-layers.md`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from pixelwright.core.color import srgb8_to_oklab

RGBA = npt.NDArray[np.uint8]
Float = npt.NDArray[np.float64]

WARM_SPAN = 140.0  # red minus blue at which a pixel counts as fully torch-lit
TIGHT = 10.0  # tight term: sigma = width / TIGHT, so each light owns its side of the room
WIDE = 3.5  # wide term: sigma = width / WIDE, so the whole room breathes with the light
WIDE_SHARE = 0.6
WARM_FLOOR = 0.35  # the wide term reaches unlit, cool areas at this share
CURVE_SCALE, CURVE_OFFSET = 0.8, 0.3  # light = amplitude * (0.8 * curve + 0.3) * mask: biased up
FLAME_RAMP = ((255, 250, 210), (255, 235, 150), (255, 200, 90), (240, 150, 50))  # core -> orange
FLAME_W = 13
FLAME_GREEN = 180  # green channel at which a warm pixel is flame, not lit wall
MAX_LOOP = 1200  # frames: a longer common loop means the cycles were badly chosen


def flicker_curve(period: int, phases: tuple[float, float, float]) -> Float:
    """One light's level per frame (about -1.1..1.1), looping over `period` frames: three
    harmonics, so it never reads as a plain pulse."""
    q = 2 * np.pi * np.arange(period) / period
    p0, p1, p2 = phases
    return 0.6 * np.sin(q + p0) + 0.3 * np.sin(3 * q + p1) + 0.2 * np.sin(5 * q + p2)


def light_mask(img: RGBA, x: float, y: float, width: int) -> tuple[Float, float]:
    """A light's reach (H x W, 0-1) and its peak before normalising: a tight term weighted by
    how torch-lit each pixel already is, plus a wide, weaker term that also reaches the cool
    parts of the room."""
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    rgb = img[..., :3].astype(np.float64)
    warm = np.clip((rgb[..., 0] - rgb[..., 2]) / WARM_SPAN, 0, 1)
    d2 = (xx - x) ** 2 + (yy - y) ** 2
    tight = np.exp(-d2 / (2 * (width / TIGHT) ** 2)) * warm
    wide = (
        WIDE_SHARE
        * np.exp(-d2 / (2 * (width / WIDE) ** 2))
        * (WARM_FLOOR + (1 - WARM_FLOOR) * warm)
    )
    mask = tight + wide
    peak = float(mask.max()) or 1.0
    return mask / peak, peak


def loop_length(cycles: list[int]) -> int:
    """The shortest preview in which every cycle closes: their least common multiple."""
    n = 1
    for c in cycles:
        n = math.lcm(n, max(1, c))
    return n


def palette_of(img: RGBA) -> RGBA:
    """The image's opaque colours (N x 3)."""
    return np.unique(img[img[..., 3] > 0][:, :3], axis=0)


def nearest(palette: RGBA, targets: npt.ArrayLike) -> RGBA:
    """For each target colour, the palette colour nearest to it in OKLab: effect colours are
    picked from the palette, never written by hand (hand-picked blues snapped to pink)."""
    pal = srgb8_to_oklab(palette)
    lab = srgb8_to_oklab(np.asarray(targets, np.float64).reshape(-1, 3))
    best = np.argmin(((lab[:, None, :] - pal[None, :, :]) ** 2).sum(-1), axis=1)
    out: RGBA = palette[best]
    return out


def snap(rgb: Float, palette: RGBA) -> RGBA:
    """Every pixel (H x W x 3, 0-255 floats) to the nearest palette colour."""
    colours, back = np.unique(
        np.rint(rgb.reshape(-1, 3)).astype(np.int64), axis=0, return_inverse=True
    )  # solve once per distinct colour, not per pixel
    pal = palette.astype(np.int64)
    best = np.empty(len(colours), np.intp)
    for a in range(0, len(colours), 4096):
        c = colours[a : a + 4096]
        best[a : a + 4096] = np.argmin(((c[:, None] - pal[None]) ** 2).sum(-1), 1)
    out: RGBA = palette[best][back.ravel()].reshape(rgb.shape)
    return out


def flame_pixels(img: RGBA, box: tuple[int, int, int, int]) -> npt.NDArray[np.bool_]:
    """The painted flame inside `box` (x, y, w, h): its yellow-to-white pixels (H x W). A
    torch-lit wall is orange, not yellow, so it stays."""
    x, y, w, h = box
    hot = (img[..., 3] > 0) & (img[..., 1] >= FLAME_GREEN)
    mask = np.zeros(img.shape[:2], bool)
    mask[y : y + h, x : x + w] = hot[y : y + h, x : x + w]
    return mask


def fill_from_row(img: RGBA, mask: npt.NDArray[np.bool_], reach: int = 10) -> RGBA:
    """`img` with the masked pixels taken from the nearest unmasked pixel in the same row:
    the painted flame removed, the wall behind it continued."""
    out = img.copy()
    w = img.shape[1]
    for y, x in zip(*np.nonzero(mask), strict=True):
        for d in range(1, reach):
            hit = [c for c in (x - d, x + d) if 0 <= c < w and not mask[y, c]]
            if hit:
                out[y, x] = img[y, hit[0]]
                break
    return out


@dataclass(frozen=True)
class FlameSprite:
    left: int
    top: int
    frames: list[RGBA]


def flame_frames(
    base_x: float, base_y: int, height: int, curve: Float, ramp: RGBA, phase: float = 0.0
) -> FlameSprite:
    """A flame drawn from a shape, one frame per curve step: a teardrop widest a third of the
    way up, a tongue that sways more the higher it goes, heat noise rising through it that
    closes the loop, no dark rim. Its light's curve drives it: brighter = taller and yellower."""
    period = len(curve)
    hmax = int(np.ceil(height * 1.1))
    left, top = round(base_x) - FLAME_W // 2, base_y - hmax - 3
    u = np.arange(FLAME_W)[None, :] - FLAME_W // 2
    rows = np.arange(hmax + 4)[:, None] + top
    ramp_f = ramp.astype(np.float64)
    frames = []
    for t in range(period):
        vn = (float(curve[t]) + 1.1) / 2.2  # 0 calm .. 1 strongest
        hf = height * (0.9 + 0.2 * vn)
        v = (base_y - rows) / hf  # 0 at the base, 1 at the tip
        p = 2 * np.pi * t / period + phase
        sway = 1.3 * (1.1 * np.sin(p) + 0.5 * np.sin(2 * p + 1.3) + 0.3 * np.sin(3 * p + 0.4))
        sway = sway * np.clip(v, 0, None) ** 1.6
        width = 5.4 * np.clip(v + 0.15, 0, None) ** 0.4 * np.clip(1.05 - v, 0, None) ** 1.1
        width = width * (1 + 0.06 * np.sin(2 * p + 0.7))
        noise = 0.5 * np.sin(2 * np.pi * (v * hf / 5.0 - 3 * t / period) + u * 0.9) + 0.5 * np.sin(
            2 * np.pi * (v * hf / 3.3 - 4 * t / period) - u * 1.4 + 1
        )  # scrolls whole wavelengths per cycle: the loop is seamless
        heat = 1 - np.abs(u - sway) / np.maximum(width, 1e-3)
        heat = heat + 0.3 * noise * np.clip(v, 0.2, 1) - 0.2 * np.clip(v, 0, None)
        heat = np.where(v < -0.12, -1, heat)
        on = heat > 0
        vv = np.broadcast_to(np.clip(v, 0, 1), heat.shape)
        k = np.clip((1 - heat[on]) * 4.0 + 1.6 * vv[on] - 0.4 - 1.2 * vn, 0, len(ramp) - 1)
        fr = np.zeros((hmax + 4, FLAME_W, 4), np.uint8)
        fr[on, :3] = ramp_f[k.astype(int)]
        fr[on, 3] = 255
        frames.append(fr)
    return FlameSprite(left, top, frames)


def brightness_swing(means: list[float]) -> float:
    """How much the mean brightness moves over the loop, as a share of its average."""
    if not means:
        return 0.0
    return (max(means) - min(means)) / max(1e-9, float(np.mean(means)))
