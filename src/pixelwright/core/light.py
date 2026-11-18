"""Relight a finished pixel-art image without adding colours: vignettes and flickering lights.

Every changed pixel takes the image's own colour of the same hue that is nearest to the new
lightness, the way 1990s adventures cycled palette entries. A pixel with no colour of its
hue at the new lightness stays as it was, so dark walls never turn grey around a torch, and
the brightest pixels (the flame itself) keep their colours.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from pixelwright.core.color import srgb8_to_oklab

RGBA = npt.NDArray[np.uint8]
HUE_WEIGHT = 6.0  # a step in hue costs this much more than the same step in lightness
HUE_LIMIT = 0.012  # OKLab distance from a pixel's hue beyond which no colour has its hue
CHROMA_SHARE = 0.3  # how much a change of saturation along the hue still costs
NEUTRAL = 0.03  # chroma below which a colour counts as grey
FLAME_L = 0.85  # pixels this light are the light source: they keep their colour
LIGHT_FRAMES = 8
STEP = 0.002  # lightness changes are solved in steps this fine


@dataclass(frozen=True)
class Light:
    x: float
    y: float
    radius: float = 110.0
    strength: float = 0.15  # OKLab lightness added at the centre at full flicker

    def __post_init__(self) -> None:
        if self.radius <= 0:
            raise ValueError(f"light radius must be above 0 (got {self.radius:g})")
        if not 0 < self.strength <= 1:
            raise ValueError(f"light strength must be in (0, 1] (got {self.strength:g})")


def relight(img: RGBA, delta: npt.NDArray[np.float64]) -> RGBA:
    """`img` with each pixel's lightness moved by `delta` (H x W), in its own colours."""
    out = img.copy()
    opaque = img[..., 3] > 0
    pal = np.unique(img[opaque][:, :3], axis=0)
    pal_lab = srgb8_to_oklab(pal)
    lab = srgb8_to_oklab(img[..., :3])
    todo = opaque & (np.abs(delta) > 0.004) & (lab[..., 0] < FLAME_L)
    if not todo.any():
        return out
    # light scales with the surface: a lit wall brightens, the black void beside it does not
    shift = delta[todo] * np.clip(lab[todo][:, 0] / 0.55, 0, 1) ** 2
    # solve once per (colour, lightness step), not per pixel: a wide scene stays light on memory
    _, colour = np.unique(img[todo][:, :3], axis=0, return_inverse=True)
    pairs, back = np.unique(
        np.stack([colour.ravel(), np.rint(shift / STEP).astype(np.int64)], 1), axis=0,
        return_inverse=True,
    )  # fmt: skip
    first = np.zeros(len(pairs), np.int64)
    first[back.ravel()] = np.arange(len(back.ravel()))
    target = lab[todo][first].copy()
    target[:, 0] += pairs[:, 1] * STEP
    # a lit wall may warm up but never reach the flame's own white-yellow: the fire stays brightest
    target[:, 0] = np.minimum(target[:, 0], np.maximum(lab[todo][first][:, 0], FLAME_L - 0.08))
    hue = _hue_distance(target[:, 1:], pal_lab[:, 1:])
    light_gap = (target[:, None, 0] - pal_lab[None, :, 0]) ** 2
    best = np.argmin(light_gap + HUE_WEIGHT * hue, axis=1)
    alien = hue[np.arange(len(best)), best] > HUE_LIMIT**2
    choice = pal[best]
    choice[alien] = img[todo][first][alien][:, :3]
    new = choice[back.ravel()]
    out[todo, :3] = new
    return out


def _hue_distance(
    ab: npt.NDArray[np.float64], pal_ab: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """Squared distance of each palette colour from each pixel's hue line (N x P): a ramp's
    darker, less saturated shades lie on it; a grey near a dark purple does not. Near-grey
    pixels compare plain chroma instead, their hue being noise."""
    plain = ((ab[:, None, :] - pal_ab[None, :, :]) ** 2).sum(-1)
    c = np.linalg.norm(ab, axis=1)
    unit = ab / np.maximum(c, 1e-9)[:, None]
    along = unit @ pal_ab.T
    across = (pal_ab[None, :, 0] * unit[:, None, 1] - pal_ab[None, :, 1] * unit[:, None, 0]) ** 2
    hued = np.where(along > 0, across, plain)  # the opposite hue is never the same one
    return np.where((c > NEUTRAL)[:, None], hued + CHROMA_SHARE * plain, plain)


def vignette(img: RGBA, strength: float) -> RGBA:
    """Darken towards the corners, `strength` OKLab lightness at the corners."""
    if not 0 <= strength <= 1:
        raise ValueError(f"vignette must be in [0, 1] (got {strength:g})")
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot((xx - (w - 1) / 2) / (w / 2), (yy - (h - 1) / 2) / (h / 2)) / np.sqrt(2)
    return relight(img, -strength * np.clip((r - 0.35) / 0.65, 0, 1) ** 1.5)


def flicker(lights: list[Light], frame: int, frames: int = LIGHT_FRAMES) -> list[float]:
    """Each light's level (0-1) at `frame`: its own rhythm, looping over `frames`."""
    t = 2 * np.pi * frame / frames
    return [
        float(0.55 + 0.25 * np.sin(t * (1 + i % 2) + 1.7 * i) + 0.2 * np.sin(3 * t + 0.9 * i))
        for i in range(len(lights))
    ]


def light_frame(img: RGBA, lights: list[Light], frame: int, frames: int = LIGHT_FRAMES) -> RGBA:
    """`img` lit by `lights` at one moment: the surroundings brighten and dim with the flame."""
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    delta = np.zeros((h, w))
    for light, level in zip(lights, flicker(lights, frame, frames), strict=True):
        d = np.hypot(xx - light.x, (yy - light.y) * 1.3)
        delta += light.strength * level * np.clip(1 - d / light.radius, 0, 1) ** 2
    return relight(img, delta)


@dataclass(frozen=True)
class Flame:
    """A painted flame to animate in place: the box (x, y, w, h) that holds it."""

    x: int
    y: int
    w: int
    h: int

    def __post_init__(self) -> None:
        if self.w < 2 or self.h < 2:
            raise ValueError(f"a flame box needs 2x2 px or more (got {self.w}x{self.h})")


FLAME_MIN_L = 0.6  # flame pixels are this light and warm (or near white)
FLAME_WARM_B = 0.03


def flame_frame(img: RGBA, flame: Flame, frame: int, frames: int = LIGHT_FRAMES) -> RGBA:
    """`img` with the flame in `flame`'s box alive at `frame`: its own colours flow upwards
    (palette cycling by heat) and the coolest tips come and go, showing what is behind."""
    out = img.copy()
    sub = out[flame.y : flame.y + flame.h, flame.x : flame.x + flame.w]
    lab = srgb8_to_oklab(sub[..., :3])
    lit = lab[..., 0]
    mask = (sub[..., 3] > 0) & (
        ((lit > FLAME_MIN_L) & (lab[..., 2] > FLAME_WARM_B)) | (lit > FLAME_L)
    )
    if mask.sum() < 2:
        return out
    colours, idx = np.unique(sub[mask][:, :3], axis=0, return_inverse=True)
    order = np.argsort(srgb8_to_oklab(colours)[:, 0])
    ramp = colours[order]  # the flame's own colours, dark to light
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))
    heat = rank[idx.ravel()] / max(1, len(ramp) - 1)
    ys, xs = np.nonzero(mask)
    t = 2 * np.pi * frame / frames
    wave = 0.5 * np.sin(1.1 * ys + 2 * t) * np.cos(0.9 * xs - t) + 0.5 * np.sin(0.7 * ys + 3 * t)
    hot = np.clip(heat + 0.22 * wave, 0, 1)
    sub[ys, xs, :3] = ramp[np.rint(hot * (len(ramp) - 1)).astype(int)]
    top = ys.min() + 0.5 * (ys.max() - ys.min())
    gone = (hot < 0.15) & (ys < top)  # a cool tip flickers out: show the pixel beside it
    for y, x in zip(ys[gone], xs[gone], strict=True):
        row = np.nonzero(~mask[y])[0]
        if len(row):
            sub[y, x] = sub[y, row[np.argmin(np.abs(row - x))]]
    return out
