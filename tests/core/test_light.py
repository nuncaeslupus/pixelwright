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


def test_bad_light_settings_are_refused() -> None:
    import pytest

    for radius, strength in ((0, 0.2), (-5, 0.2), (40, 0), (40, 2)):
        with pytest.raises(ValueError):
            Light(1, 1, radius, strength)
    with pytest.raises(ValueError):
        vignette(_wall(), 1.5)


def test_wide_scene_relights_without_a_pixel_by_colour_matrix() -> None:
    import tracemalloc

    rng = np.random.default_rng(0)
    img = np.zeros((180, 960, 4), np.uint8)
    img[..., 3] = 255
    shades = np.array([[40 + i, 25 + i // 2, 20 + i // 3] for i in range(200)], np.uint8)
    img[..., :3] = shades[rng.integers(0, 200, (180, 960))]
    tracemalloc.start()
    light_frame(img, [Light(480, 90, 400, 0.3)], 2)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert peak < 200 * 2**20  # was about 1 GB solved per pixel


def test_a_flame_flows_in_its_own_colours_inside_its_box() -> None:
    from pixelwright.core.light import Flame, flame_frame

    img = np.zeros((30, 30, 4), np.uint8)
    img[..., :3] = (30, 20, 40)
    img[..., 3] = 255
    fire = [(200, 110, 30), (235, 160, 50), (250, 210, 90), (255, 245, 200)]
    for row in range(12):  # hotter towards the base
        img[10 + row, 12:18, :3] = fire[min(3, row // 3)]
    flame = Flame(10, 8, 10, 16)
    frames = [flame_frame(img, flame, i) for i in range(8)]
    assert len({f.tobytes() for f in frames}) > 1
    for f in frames:
        assert _colours(f) <= _colours(img)
        outside = np.ones((30, 30), bool)
        outside[8:24, 10:20] = False
        assert (f[outside] == img[outside]).all()
