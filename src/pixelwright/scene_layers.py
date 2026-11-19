"""`pw scene layers`: a scene split the way a game engine loads it.

Writes `<export>/scenes/<name>-layers/`: the static background (painted flames removed),
one sprite strip per layer and per flame, one light mask per light, a floor mask,
`manifest.json`, and `preview.gif` composed the way an engine would, with every frame
snapped to the scene palette. Guide: `docs/guide/scene-layers.md`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageDraw

from pixelwright.core import layered as ly
from pixelwright.project import Project
from pixelwright.scene import (
    SCENES_DIR,
    Scene,
    SceneError,
    _pick_size,
    asset_image,
    background_image,
    opaque_box,
)

RGBA = npt.NDArray[np.uint8]
DEFAULT_PERIODS = (48, 60)  # frames at 10 fps: two lights never move in step
DEFAULTS: dict[str, Any] = {
    "fps": 10,
    "amplitude": 0.26,
    "tint": [1.0, 0.92, 0.85],  # red moves most: brighter reads warmer
    "floor_gain": 2.2,  # light pools on the floor answer the flicker most
    "frames": None,  # preview length; default: the common loop of every cycle
    "seed": 5,
}
LUMA = np.array([0.3, 0.59, 0.11])


@dataclass
class Engine:
    fps: int
    amplitude: float
    tint: tuple[float, float, float]
    floor_gain: float
    frames: int | None
    seed: int

    @classmethod
    def of(cls, scene: Scene) -> Engine:
        raw = {**DEFAULTS, **scene.engine}
        unknown = set(scene.engine) - set(DEFAULTS)
        if unknown:
            raise SceneError(f"{scene.path}: [engine] has no {', '.join(sorted(unknown))}")
        try:
            tint = tuple(float(v) for v in raw["tint"])
            eng = cls(
                int(raw["fps"]),
                float(raw["amplitude"]),
                (tint[0], tint[1], tint[2]),
                float(raw["floor_gain"]),
                None if raw["frames"] is None else int(raw["frames"]),
                int(raw["seed"]),
            )
        except (TypeError, ValueError, IndexError) as exc:
            raise SceneError(f"{scene.path}: malformed [engine] ({exc})") from exc
        if eng.fps < 1 or not 0 < eng.amplitude <= 1 or eng.floor_gain < 1:
            raise SceneError(
                f"{scene.path}: [engine] needs fps >= 1, 0 < amplitude <= 1, floor_gain >= 1"
            )
        return eng


@dataclass
class Sheet:
    name: str
    frames: list[RGBA]
    pos: tuple[int, int]
    z: float
    fps: int

    def manifest(self) -> dict[str, Any]:
        h, w = self.frames[0].shape[:2]
        return {
            "name": self.name,
            "sheet": f"{self.name}.png",
            "frame": [w, h],
            "frames": len(self.frames),
            "fps": self.fps,
            "pos": list(self.pos),
            "z": self.z,
            "loop": True,
        }


@dataclass
class Split:
    background: RGBA
    palette: RGBA
    sheets: list[Sheet]
    masks: list[npt.NDArray[np.float64]]
    curves: list[npt.NDArray[np.float64]]
    floor: npt.NDArray[np.float64]
    manifest: dict[str, Any]
    frames: int
    warnings: list[str] = field(default_factory=list)


def _cycle(frames: int, fps: int, base_fps: int) -> int:
    """A strip's loop in preview frames; it must be a whole number of them."""
    span = frames * base_fps / fps
    if abs(span - round(span)) > 1e-9:
        raise SceneError(
            f"a {frames}-frame strip at {fps} fps is not a whole number of {base_fps} fps frames"
        )
    return round(span)


def floor_mask(scene: Scene, shape: tuple[int, int]) -> npt.NDArray[np.float64]:
    """1 on the walkable floor (the `floor` polygon, else everything below the horizon)."""
    h, w = shape
    if scene.floor:
        im = Image.new("L", (w, h), 0)
        ImageDraw.Draw(im).polygon([tuple(p) for p in scene.floor], fill=255)
        return np.asarray(im, np.float64) / 255
    rows = np.clip((np.arange(h) - scene.horizon) / 4, 0, 1)
    return np.repeat(rows[:, None], w, axis=1)


def split(scene: Scene, project: Project) -> Split:
    eng = Engine.of(scene)
    painted = background_image(scene, project)
    palette = ly.palette_of(painted)
    if not len(palette):
        raise SceneError(f"{scene.name}: the background has no opaque pixels")
    h, w = painted.shape[:2]
    view_w = scene.viewport[0]
    # one curve per light: its flame (if any) and its light both follow it
    rng = np.random.default_rng(eng.seed)
    curves: list[npt.NDArray[np.float64]] = []
    masks: list[npt.NDArray[np.float64]] = []
    lights_out: list[dict[str, Any]] = []
    for i, light in enumerate(scene.lights):
        period = light.period or DEFAULT_PERIODS[i % len(DEFAULT_PERIODS)]
        phases = rng.uniform(0, 6.3, 3)
        curves.append(ly.flicker_curve(period, (phases[0], phases[1], phases[2])))
        mask, peak = ly.light_mask(painted, light.x, light.y, view_w)
        masks.append(mask)
        lights_out.append(
            {
                "name": f"light-{i}",
                "pos": [round(light.x), round(light.y)],
                "mask": f"light-{i}.png",
                "flicker": {
                    "amplitude": round(eng.amplitude * peak, 4),
                    "tint": list(eng.tint),
                    "period_frames": period,
                    "fps": eng.fps,
                    "follows": None,
                    "scale": ly.CURVE_SCALE,
                    "offset": ly.CURVE_OFFSET,
                    "curve": [round(float(v), 3) for v in curves[-1]],
                },
            }
        )
    # flames: cut out of the background, redrawn from a shape, driven by their light's curve
    sheets: list[Sheet] = []
    cut = np.zeros((h, w), bool)
    ramp = ly.nearest(palette, ly.FLAME_RAMP)
    warnings: list[str] = []
    for j, flame in enumerate(scene.flames):
        pix = ly.flame_pixels(painted, (flame.x, flame.y, flame.w, flame.h))
        if not pix.any():
            warnings.append(f"flame-{j}: no flame pixels in its box; drawn over the background")
        cut |= pix
        ys, xs = (
            np.nonzero(pix)
            if pix.any()
            else (np.array([flame.y + flame.h - 1]), np.array([flame.x + flame.w / 2]))
        )
        if not scene.lights:
            raise SceneError(f"{scene.name}: flame-{j} needs a [[light]] to drive it")
        li = (
            flame.light
            if flame.light is not None
            else int(
                np.argmin([np.hypot(lt.x - xs.mean(), lt.y - ys.mean()) for lt in scene.lights])
            )
        )
        sprite = ly.flame_frames(
            float(xs.mean()),
            int(ys.max()),
            flame.height or flame.h,
            curves[li],
            ramp,
            phase=2.1 * j,
        )
        sheets.append(Sheet(f"flame-{j}", sprite.frames, (sprite.left, sprite.top), 10, eng.fps))
        if lights_out[li]["flicker"]["follows"] is None:
            lights_out[li]["flicker"]["follows"] = f"flame-{j}"
    background = ly.fill_from_row(painted, cut) if cut.any() else painted
    # props and characters: their own strips, placed by their base like `pw scene compose`
    for layer in scene.layers_in_order():
        if layer.sizes:
            ref, img, warn = _pick_size(scene, project, layer)
            warnings += warn
        else:
            ref = layer.states.get(layer.state) or layer.asset or ""
            img = asset_image(project, ref)
        n = layer.frames.get(layer.state, 1)
        fw = img.shape[1] // n
        strip = [img[:, k * fw : (k + 1) * fw] for k in range(n)]
        left_box, _, right_box, bottom = opaque_box(strip[0])
        x, y = layer.at
        pos = (x - (left_box + right_box) // 2, y - bottom)
        sheets.append(Sheet(layer.name, strip, pos, layer.order, eng.fps))
    floor = floor_mask(scene, (h, w))
    cycles = [len(c) for c in curves] + [_cycle(len(s.frames), s.fps, eng.fps) for s in sheets]
    frames = eng.frames or ly.loop_length(cycles)
    broken = sorted({c for c in cycles if frames % c})
    if broken:
        raise SceneError(
            f"{scene.name}: a {frames}-frame preview cuts the {broken} frame "
            f"cycle(s) mid-loop; use a common multiple, e.g. "
            f"{ly.loop_length(cycles)}"
        )
    if frames > ly.MAX_LOOP:
        raise SceneError(
            f"{scene.name}: the cycles {sorted(set(cycles))} only meet after {frames} "
            f"frames; pick periods with common factors (e.g. 48 and 60)"
        )
    manifest = {
        "scene": scene.name,
        "size": [w, h],
        "fps": eng.fps,
        "background": "background.png",
        "preview_frames": frames,
        "layers": [s.manifest() for s in sheets],
        "lights": lights_out,
        "floor": {"mask": "floor.png", "flicker_gain": eng.floor_gain},
        "walkable": [list(p) for p in scene.floor] or None,
        "palette": len(palette),
    }
    return Split(background, palette, sheets, masks, curves, floor, manifest, frames, warnings)


def preview_frame(sp: Split, t: int) -> RGBA:
    """Frame `t` the way an engine composes it: lights multiply the background (more on the
    floor), sprites on top by z, then every pixel snapped to the scene palette."""
    eng_fps = sp.manifest["fps"]
    h, w = sp.background.shape[:2]
    light = np.zeros((h, w))
    for mask, curve, meta in zip(sp.masks, sp.curves, sp.manifest["lights"], strict=True):
        v = float(curve[t % len(curve)])
        light += meta["flicker"]["amplitude"] * (ly.CURVE_SCALE * v + ly.CURVE_OFFSET) * mask
    light *= 1 + (sp.manifest["floor"]["flicker_gain"] - 1) * sp.floor
    tint = np.array(sp.manifest["lights"][0]["flicker"]["tint"] if sp.masks else [1, 1, 1])
    rgb = np.clip(sp.background[..., :3] * (1 + light[..., None] * tint), 0, 255)
    for s in sorted(sp.sheets, key=lambda s: s.z):
        k = t * s.fps // eng_fps % len(s.frames)
        img = s.frames[k]
        x0, y0 = s.pos
        sx0, sy0 = max(0, -x0), max(0, -y0)
        dx0, dy0 = max(0, x0), max(0, y0)
        dx1, dy1 = min(w, x0 + img.shape[1]), min(h, y0 + img.shape[0])
        if dx0 >= dx1 or dy0 >= dy1:
            continue
        src = img[sy0 : sy0 + dy1 - dy0, sx0 : sx0 + dx1 - dx0]
        on = src[..., 3] > 127  # pixel art keeps hard edges
        rgb[dy0:dy1, dx0:dx1][on] = src[on][:, :3]
    out = np.zeros((h, w, 4), np.uint8)
    out[..., :3] = ly.snap(rgb, sp.palette)
    out[..., 3] = sp.background[..., 3]
    return out


def write_layers(
    scene: Scene, project: Project, *, zoom: int = 1
) -> tuple[list[Path], dict[str, Any], list[str]]:
    sp = split(scene, project)
    folder = project.export_dir / SCENES_DIR / f"{scene.name}-layers"
    folder.mkdir(parents=True, exist_ok=True)

    def save(img: RGBA, name: str, mode: str = "RGBA") -> Path:
        path = folder / name
        Image.fromarray(img, mode).save(path)
        return path

    paths = [save(sp.background, "background.png")]
    for s in sp.sheets:
        paths.append(save(np.concatenate(s.frames, axis=1), f"{s.name}.png"))
    for i, mask in enumerate(sp.masks):
        paths.append(save((mask * 255).astype(np.uint8), f"light-{i}.png", "L"))
    paths.append(save((sp.floor * 255).astype(np.uint8), "floor.png", "L"))
    pal = {tuple(c) for c in sp.palette.tolist()}
    seen: set[tuple[int, ...]] = set()
    means, frames = [], []
    for t in range(sp.frames):
        fr = preview_frame(sp, t)
        opaque = fr[..., 3] > 0
        seen |= {tuple(c) for c in np.unique(fr[opaque][:, :3], axis=0).tolist()}
        means.append(float((fr[opaque][:, :3] @ LUMA).mean()) if opaque.any() else 0.0)
        im = Image.fromarray(fr, "RGBA")
        if zoom > 1:
            im = im.resize((fr.shape[1] * zoom, fr.shape[0] * zoom), Image.Resampling.NEAREST)
        frames.append(im)
    gif = folder / "preview.gif"
    frames[0].save(
        gif,
        save_all=True,
        append_images=frames[1:],
        duration=1000 // sp.manifest["fps"],
        loop=0,
        disposal=2,
    )
    report = {
        "preview_frames": sp.frames,
        "colours_used": len(seen),
        "off_palette": len(seen - pal),
        "brightness_swing": round(ly.brightness_swing(means), 4),
    }
    manifest = {**sp.manifest, "checks": report}
    data = folder / "manifest.json"
    data.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    paths += [gif, data]
    return paths, manifest, sp.warnings
