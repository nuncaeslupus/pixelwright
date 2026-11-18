"""Lights and vignettes move pixels along the image's own colours, never adding one."""

from __future__ import annotations

import numpy as np

from pixelwright.core.light import Light, light_frame, vignette

# a wall in five shades of one warm brown, plus a cold blue the wall never turns into
RAMP = [(60, 35, 25), (90, 55, 38), (120, 75, 50), (150, 98, 66), (180, 122, 84)]
BLUE = (40, 50, 110)


def _wall() -> np.ndarray:
    img = np.zeros((60, 100, 4), np.uint8)
    img[..., :3] = RAMP[2]
    img[..., 3] = 255
    img[0, :5, :3] = RAMP  # the other shades exist somewhere in the image
    img[50:, 80:, :3] = BLUE
    return img


def _colours(img: np.ndarray) -> set[tuple[int, ...]]:
    return {tuple(int(v) for v in c) for c in img[..., :3].reshape(-1, 3)}


def test_a_light_brightens_its_surroundings_in_their_own_colours() -> None:
    img = _wall()
    frames = [light_frame(img, [Light(30, 30, 40, 0.3)], i) for i in range(8)]
    for f in frames:
        assert _colours(f) <= _colours(img)
        assert (f[30, 95] == img[30, 95]).all()  # beyond the radius nothing moves
        assert (f[55, 90] == img[55, 90]).all()  # no blue turns brown
    near = {tuple(int(v) for v in f[30, 32, :3]) for f in frames}
    assert len(near) > 1 and near <= set(RAMP)  # it flickers along the ramp


def test_vignette_darkens_corners_only() -> None:
    img = _wall()
    out = vignette(img, 0.2)
    assert _colours(out) <= _colours(img)
    assert tuple(int(v) for v in out[59, 0, :3]) in RAMP[:2]
    assert (out[30, 50] == img[30, 50]).all()
