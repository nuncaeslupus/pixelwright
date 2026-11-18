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


@dataclass(frozen=True)
class Light:
    x: float
    y: float
    radius: float = 110.0
    strength: float = 0.15  # OKLab lightness added at the centre at full flicker


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
    target = lab[todo].copy()
    # light scales with the surface: a lit wall brightens, the black void beside it does not
    target[:, 0] += delta[todo] * np.clip(target[:, 0] / 0.55, 0, 1) ** 2
    hue = _hue_distance(target[:, 1:], pal_lab[:, 1:])
    light_gap = (target[:, None, 0] - pal_lab[None, :, 0]) ** 2
    best = np.argmin(light_gap + HUE_WEIGHT * hue, axis=1)
    alien = hue[np.arange(len(best)), best] > HUE_LIMIT**2
    new = pal[best]
    new[alien] = img[todo][alien][:, :3]
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
