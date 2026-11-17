"""Palettes built as ramps: each key colour (skin, wood, stone…) becomes a short run of
shades from shadow to light, the way pixel artists build palettes by hand.

Along a ramp the lightness changes and so does the hue: shadows turn towards blue-violet
and lose some chroma, lights turn towards yellow (hue shifting). Ramps that share their
ends (one cool near-black, one warm near-white) read as one palette.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from pixelwright.core.color import (
    oklab_to_oklch,
    oklab_to_srgb,
    oklab_to_srgb8,
    oklch_to_oklab,
    srgb8_to_oklab,
)
from pixelwright.core.palette import Color, Palette

SHADOW_HUE = 285.0  # OKLCH: blue-violet
LIGHT_HUE = 95.0  # warm yellow
HUE_SHIFT = 25.0  # degrees turned at the ends of a ramp
DARKEST, LIGHTEST = 0.26, 0.95  # OKLab lightness bounds of a ramp (the ink is darker)
SPAN_DOWN, SPAN_UP = 0.32, 0.26  # how far a ramp reaches below and above its key
FADE_DOWN, FADE_UP = 0.35, 0.5  # chroma lost at the dark and light ends
ENDS = ("1b1726", "f4ecd8")  # the shared near-black and near-white

# A base for a point-and-click adventure: people, places, props and a few accents.
ADVENTURE = {
    "skin-light": "f0c39c",
    "skin-mid": "c68a62",
    "skin-dark": "7d4c34",
    "hair": "6b4a2e",
    "wood": "8a5a3a",
    "stone": "8a857e",
    "metal": "98a0a8",
    "foliage": "5a8a3a",
    "cloth-red": "a8323c",
    "cloth-blue": "3c5a9a",
    "gold": "d4a640",
    "fire": "e8682a",
}
PRESETS = {"adventure": ADVENTURE}
FloatArray = npt.NDArray[np.float64]


def _rgb(hexa: str) -> tuple[int, int, int]:
    hexa = hexa.lstrip("#").lower()
    if len(hexa) != 6:
        raise ValueError(f"not a colour: {hexa!r} (want rrggbb)")
    return int(hexa[0:2], 16), int(hexa[2:4], 16), int(hexa[4:6], 16)


def _towards(hue: float, target: float, degrees: float) -> float:
    """`hue` turned by up to `degrees` towards `target`, the short way round."""
    diff = (target - hue + 180.0) % 360.0 - 180.0
    return (hue + float(np.clip(diff, -degrees, degrees))) % 360.0


def _in_gamut(light: float, c: float, h: float) -> tuple[int, int, int]:
    """The OKLCH colour as 8-bit sRGB, chroma reduced until it fits."""
    for _ in range(30):
        srgb = oklab_to_srgb(oklch_to_oklab(np.array([light, c, h])))
        if (srgb >= -1e-4).all() and (srgb <= 1 + 1e-4).all():
            break
        c *= 0.9
    r, g, b = oklab_to_srgb8(oklch_to_oklab(np.array([light, c, h])))
    return int(r), int(g), int(b)


def ramp(key: str, steps: int = 5) -> list[tuple[int, int, int]]:
    """`steps` shades of the hex colour `key`, dark to light, the key in the middle."""
    if steps < 2:
        raise ValueError("a ramp needs at least 2 steps")
    l0, c0, h0 = oklab_to_oklch(srgb8_to_oklab(np.array(_rgb(key), np.uint8)))
    low, high = max(DARKEST, l0 - SPAN_DOWN), min(LIGHTEST, l0 + SPAN_UP)
    out = []
    for t in np.linspace(-1.0, 1.0, steps):
        if t < 0:
            light = l0 + t * (l0 - low)
            c = c0 * (1 - FADE_DOWN * -t)
            h = _towards(h0, SHADOW_HUE, HUE_SHIFT * -t)
        else:
            light = l0 + t * (high - l0)
            c = c0 * (1 - FADE_UP * t)
            h = _towards(h0, LIGHT_HUE, HUE_SHIFT * t)
        out.append(_in_gamut(float(light), float(c), float(h)))
    return out


def ramp_palette(keys: dict[str, str], steps: int = 5, *, ends: bool = True) -> Palette:
    """One ramp per named key colour (`name-1` darkest), then the shared ends."""
    colors: list[Color] = []
    seen: set[tuple[int, int, int]] = set()

    def add(rgb: tuple[int, int, int], name: str) -> None:
        if rgb not in seen:
            seen.add(rgb)
            colors.append(Color(*rgb, name=name))

    for name, key in keys.items():
        for i, rgb in enumerate(ramp(key, steps), 1):
            add(rgb, f"{name}-{i}")
    if ends:
        add(_rgb(ENDS[0]), "ink")
        add(_rgb(ENDS[1]), "paper")
    return Palette(tuple(colors), columns=steps)  # one ramp per row


KEY_LIGHT = (0.45, 0.75)  # OKLab lightness range of a key taken from images
VIVID = 0.8  # a key's chroma: this weighted percentile of its family's
NEUTRAL = 0.03  # OKLab chroma below which a colour is a grey (one family of its own)


def hue_families(lab: FloatArray, weight: FloatArray, n: int) -> dict[str, str]:
    """Key colours for `n` ramps from OKLab pixels: k-means on hue and chroma only (a, b),
    so a family holds a material's darks and lights; each key is the family's weighted
    mean hue at its median lightness (kept to a mid-tone) and its vivid-end chroma.
    Greys make one family."""
    grey = np.hypot(lab[:, 1], lab[:, 2]) < NEUTRAL
    keys: dict[str, str] = {}
    if grey.any() and weight[grey].sum() > 0.02 * weight.sum():
        keys["grey"] = _key(lab[grey], weight[grey])
        n -= 1
    ab, w = lab[~grey][:, 1:], weight[~grey]
    if n < 1 or len(ab) == 0:
        return keys
    rng = np.random.default_rng(0)
    centres = ab[rng.choice(len(ab), min(n, len(ab)), replace=False, p=w / w.sum())]
    for _ in range(25):
        near = np.argmin(((ab[:, None] - centres[None]) ** 2).sum(-1), axis=1)
        for i in range(len(centres)):
            if (near == i).any():
                centres[i] = np.average(ab[near == i], axis=0, weights=w[near == i])
    families = [(w[near == i].sum(), i) for i in range(len(centres)) if (near == i).any()]
    for rank, (_, i) in enumerate(sorted(families, reverse=True), 1):
        keys[f"hue-{rank}"] = _key(lab[~grey][near == i], w[near == i])
    return keys


def _key(lab: FloatArray, weight: FloatArray) -> str:
    order = np.argsort(lab[:, 0])
    cum = np.cumsum(weight[order])
    light = lab[order][np.searchsorted(cum, cum[-1] / 2), 0]
    light = float(np.clip(light, *KEY_LIGHT))  # mid-tone, so the ramp has room both ways
    a, b = np.average(lab[:, 1:], axis=0, weights=weight)
    # the mean of a family is duller than its colours: keep its hue, at its vivid end
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    by_c = np.argsort(chroma)
    cum_c = np.cumsum(weight[by_c])
    vivid = chroma[by_c][min(len(by_c) - 1, np.searchsorted(cum_c, VIVID * cum_c[-1]))]
    norm = max(float(np.hypot(a, b)), 1e-9)
    a, b = a / norm * vivid, b / norm * vivid
    r, g, bl = oklab_to_srgb8(np.array([light, a, b]))
    return f"{int(r):02x}{int(g):02x}{int(bl):02x}"
