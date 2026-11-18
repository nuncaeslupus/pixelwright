"""Scenes built in layers: a background, props and characters with one camera and scale.

A scene is `scenes/<name>.toml` in the project (spec `status/m7/spec.md`). The floor is a
plane seen by a camera whose eye level is the horizon row, so one reference fixes the
height of a person at every depth: `h(y) = h_ref * (y - horizon) / (y_ref - horizon)`.
Layers are placed by their base (where they touch the floor), drawn far to near, and never
resampled: pixel art cannot be scaled. Contact shadows darken the floor with colours the
scene already has, so the palette does not grow.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from PIL import Image

from pixelwright.asset import FINAL, Asset, AssetError
from pixelwright.core.color import srgb8_to_oklab
from pixelwright.core.seam import join
from pixelwright.project import Project

SCENES_DIR = "scenes"
CAMERAS = ("frontal", "three-quarter", "side")
PERSON_TO_DOOR = 0.85  # a person is about 1.75 m, a door about 2.05 m
SIZE_TOLERANCE = 0.15  # warn when the nearest character size is further off than this
SIZE_STEP = 0.75  # each suggested character size is this share of the one before
SHADOW_DARKEN = 0.6  # target lightness of a shadowed pixel, as a share of its own
FRAME_MS = 120

RGBA = npt.NDArray[np.uint8]

CAMERA_WORDS = {
    "frontal": "Seen straight from the front, the same frontal camera as the room: front "
    "faces flat to the viewer, no three-quarter turn.",
    "three-quarter": "Seen in three-quarter view, turned about 45 degrees, like the room.",
    "side": "Seen from the side in flat profile, like the room.",
}


class SceneError(ValueError):
    """A scene file is missing or malformed, or names something that is not there."""


@dataclass
class Layer:
    name: str
    at: tuple[int, int]  # bottom centre: where the layer touches the floor
    asset: str | None = None
    sizes: tuple[str, ...] = ()  # a character: one asset per size, any order
    states: dict[str, str] = field(default_factory=dict)
    frames: dict[str, int] = field(default_factory=dict)  # state -> frames in its strip
    state: str = "default"
    z: float | None = None
    shadow: bool = True

    @property
    def order(self) -> float:
        return self.z if self.z is not None else float(self.at[1])


@dataclass
class Scene:
    name: str
    path: Path
    viewport: tuple[int, int]
    width: int
    horizon: float
    camera: str
    ref_y: float
    ref_height: float  # a person's height in px with feet at row ref_y
    backgrounds: list[tuple[str, int]]
    layers: list[Layer]

    def person_height(self, y: float) -> float:
        """Height in px of a person whose feet are at row `y`."""
        return self.ref_height * (y - self.horizon) / (self.ref_y - self.horizon)

    def layer(self, name: str) -> Layer:
        for layer in self.layers:
            if layer.name == name:
                return layer
        raise SceneError(f"{self.name}: no layer {name!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "viewport": list(self.viewport),
            "width": self.width,
            "horizon": self.horizon,
            "camera": self.camera,
            "person": {"y": self.ref_y, "height": self.ref_height},
            "backgrounds": [{"asset": a, "x": x} for a, x in self.backgrounds],
            "layers": [layer.name for layer in self.layers],
        }


# --- loading ----------------------------------------------------------------------------


def scene_path(project: Project, name: str) -> Path:
    return project.root / SCENES_DIR / f"{name}.toml"


def _num(raw: object, where: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise SceneError(f"{where}: expected a number, got {raw!r}")
    return float(raw)


def _pair(raw: object, where: str) -> tuple[int, int]:
    if not (isinstance(raw, list) and len(raw) == 2):
        raise SceneError(f"{where}: expected [x, y], got {raw!r}")
    return int(_num(raw[0], where)), int(_num(raw[1], where))


def _scale(raw: dict[str, Any], where: str) -> tuple[float, float]:
    if "person" in raw:
        p = raw["person"]
        return _num(p.get("y"), f"{where}.person.y"), _num(p.get("height"), f"{where}.person")
    if "door" in raw:
        d = raw["door"]
        ratio = _num(raw.get("person_to_door", PERSON_TO_DOOR), f"{where}.person_to_door")
        return _num(d.get("y"), f"{where}.door.y"), _num(d.get("height"), f"{where}.door") * ratio
    raise SceneError(f"{where}: give a person = {{y, height}} or a door = {{y, height}}")


def _layer(raw: dict[str, Any], where: str) -> Layer:
    name = str(raw.get("name") or "")
    if not name:
        raise SceneError(f"{where}: a layer needs a name")
    sizes = tuple(str(s) for s in raw.get("sizes", []))
    asset = raw.get("asset")
    if not asset and not sizes:
        raise SceneError(f"{where} ({name}): give an asset or character sizes")
    frames = {str(k): int(_num(v, f"{where}.frames")) for k, v in raw.get("frames", {}).items()}
    if any(n < 1 for n in frames.values()):
        raise SceneError(f"{where} ({name}): frames must be at least 1")
    return Layer(
        name=name,
        at=_pair(raw.get("at"), f"{where} ({name}).at"),
        asset=str(asset) if asset else None,
        sizes=sizes,
        states={str(k): str(v) for k, v in raw.get("states", {}).items()},
        frames=frames,
        state=str(raw.get("state", "default")),
        z=_num(raw["z"], f"{where}.z") if "z" in raw else None,
        shadow=bool(raw.get("shadow", True)),
    )


def parse_scene(raw: dict[str, Any], name: str, path: Path, canvas: tuple[int, int]) -> Scene:
    head = raw.get("scene", {})
    viewport = _pair(head["viewport"], "scene.viewport") if "viewport" in head else canvas
    if "horizon" not in head:
        raise SceneError(f"{path}: [scene] needs horizon = <row>")
    horizon = _num(head["horizon"], "scene.horizon")
    camera = str(head.get("camera", "frontal"))
    if camera not in CAMERAS:
        raise SceneError(f"{path}: camera must be one of {', '.join(CAMERAS)}")
    ref_y, ref_h = _scale(head.get("scale", {}), "scene.scale")
    if ref_y <= horizon or ref_h <= 0:
        raise SceneError(f"{path}: the scale reference must stand below the horizon")
    backgrounds = [
        (str(b["asset"]), int(_num(b.get("x", 0), "background.x")))
        for b in raw.get("background", [])
    ]
    if not backgrounds:
        raise SceneError(f"{path}: add a [[background]] with an asset")
    backgrounds.sort(key=lambda b: b[1])
    layers = [_layer(r, f"layer[{i}]") for i, r in enumerate(raw.get("layer", []))]
    names = [layer.name for layer in layers]
    if len(set(names)) != len(names):
        raise SceneError(f"{path}: layer names must be unique")
    width = int(_num(head.get("width", viewport[0]), "scene.width"))
    return Scene(name, path, viewport, width, horizon, camera, ref_y, ref_h, backgrounds, layers)


def load_scene(project: Project, name: str) -> Scene:
    path = scene_path(project, name)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SceneError(f"no scene {name!r} (looked for {path})") from exc
    except tomllib.TOMLDecodeError as exc:
        raise SceneError(f"{path}: {exc}") from exc
    canvas = (project.canvas["width"], project.canvas["height"])
    return parse_scene(raw, name, path, canvas)


TEMPLATE = """# Scene: {name}. Rows count from the top; `at` is where a layer touches the floor.
[scene]
horizon = {horizon}           # eye level of the camera (row)
camera = "{camera}"           # frontal | three-quarter | side
# width = 640                # wider than the viewport for a scrolling scene

[scene.scale]                # one reference fixes a person's height at every depth
door = {{ y = {door_y}, height = {door_h} }}
# person = {{ y = 172, height = 72 }}

[[background]]
asset = "{background}"
x = 0

# [[layer]]
# name = "tomb"
# asset = "props/tomb"
# at = [160, 150]
# states = {{ open = "props/tomb-open" }}
# frames = {{ open = 8 }}     # a horizontal strip of frames

# [[layer]]
# name = "knight"
# sizes = ["chars/knight", "chars/knight-m"]
# at = [80, 172]
"""


def new_scene(
    project: Project, name: str, background: str, *, horizon: int, door_y: int, door_h: int,
    camera: str = "frontal",
) -> Path:  # fmt: skip
    path = scene_path(project, name)
    if path.exists():
        raise SceneError(f"{path} exists already")
    if camera not in CAMERAS:
        raise SceneError(f"camera must be one of {', '.join(CAMERAS)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = TEMPLATE.format(
        name=name, horizon=horizon, camera=camera, door_y=door_y, door_h=door_h,
        background=background,
    )  # fmt: skip
    path.write_text(text, encoding="utf-8")
    parse_scene(
        tomllib.loads(text), name, path, (project.canvas["width"], project.canvas["height"])
    )
    return path


# --- images -----------------------------------------------------------------------------


def asset_image(project: Project, ref: str) -> RGBA:
    """An asset's final image, else its newest version; a `.png` path is read as a file."""
    if ref.lower().endswith(".png"):
        path = project.root / ref
    else:
        try:
            asset = Asset(project, project.assets_dir / ref)
        except AssetError as exc:
            raise SceneError(str(exc)) from exc
        path = asset.path / FINAL
        if not path.is_file():
            latest = asset.latest()
            if latest is None:
                raise SceneError(f"{ref}: no final image or version")
            path = asset.version_path(latest)
    if not path.is_file():
        raise SceneError(f"{ref}: {path} not found")
    with Image.open(path) as im:
        return np.asarray(im.convert("RGBA")).copy()


def opaque_box(img: RGBA) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) of the opaque pixels, right and bottom exclusive."""
    ys, xs = np.nonzero(img[..., 3] > 0)
    if not len(ys):
        return 0, 0, img.shape[1], img.shape[0]
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def figure_height(img: RGBA) -> int:
    _, top, _, bottom = opaque_box(img)
    return bottom - top


def frame_of(strip: RGBA, frames: int, index: int) -> RGBA:
    w = strip.shape[1] // frames
    i = index % frames
    return strip[:, i * w : (i + 1) * w]


# --- composing --------------------------------------------------------------------------


@dataclass
class Placed:
    name: str
    asset: str
    x: int
    y: int
    width: int
    height: int
    state: str
    frame: int
    frames: int


@dataclass
class Composed:
    image: RGBA
    placed: list[Placed]
    warnings: list[str]
    frames: int  # frames of the longest animated layer shown


def background_image(scene: Scene, project: Project) -> RGBA:
    """The backgrounds joined left to right; overlapping tiles meet along the best seam."""
    vh = scene.viewport[1]
    world: RGBA | None = None
    for ref, x in scene.backgrounds:
        tile = asset_image(project, ref)
        if tile.shape[0] != vh:
            raise SceneError(f"{ref}: background is {tile.shape[0]} px tall, the scene {vh}")
        if world is None:
            world = np.zeros((vh, max(x, 0), 4), np.uint8)
            world = np.concatenate([world, tile], axis=1)
            continue
        overlap = world.shape[1] - x
        if overlap < 0:
            world = np.concatenate([world, np.zeros((vh, -overlap, 4), np.uint8)], axis=1)
            overlap = 0
        world = join(world, tile, overlap)
    assert world is not None
    if world.shape[1] < scene.width:
        pad = np.zeros((vh, scene.width - world.shape[1], 4), np.uint8)
        world = np.concatenate([world, pad], axis=1)
    return world[:, : scene.width].copy()


def _pick_size(scene: Scene, project: Project, layer: Layer) -> tuple[str, RGBA, list[str]]:
    want = scene.person_height(layer.at[1])
    options = [(ref, asset_image(project, ref)) for ref in layer.sizes]
    ref, img = min(options, key=lambda o: abs(figure_height(o[1]) - want))
    got = figure_height(img)
    warn = []
    if want > 0 and abs(got - want) / want > SIZE_TOLERANCE:
        warn.append(
            f"{layer.name}: nearest size {ref} is {got} px tall, the scene asks {want:.0f} px "
            f"at row {layer.at[1]}; draw a size near {want:.0f} px"
        )
    return ref, img, warn


def _shadow(canvas: RGBA, cx: int, cy: int, half_w: float, scene: Scene, palette: RGBA) -> None:
    """Darken an ellipse of floor under (cx, cy) with colours from `palette` (N x 3)."""
    depth = (cy - scene.horizon) / max(1.0, scene.viewport[1] - scene.horizon)
    half_h = max(1.0, half_w * 0.3 * min(1.0, max(0.3, depth)))
    h, w = canvas.shape[:2]
    y0, y1 = max(0, int(cy - half_h)), min(h, int(cy + half_h) + 1)
    x0, x1 = max(0, int(cx - half_w)), min(w, int(cx + half_w) + 1)
    if y0 >= y1 or x0 >= x1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1]
    inside = ((xx - cx) / half_w) ** 2 + ((yy - cy) / half_h) ** 2 <= 1.0
    region = canvas[y0:y1, x0:x1]
    inside &= region[..., 3] > 0
    if not inside.any():
        return
    pal_lab = srgb8_to_oklab(palette)
    cols, inv = np.unique(region[inside][:, :3], axis=0, return_inverse=True)
    out = cols.copy()
    for i, c in enumerate(srgb8_to_oklab(cols)):
        target = c * np.array([SHADOW_DARKEN, 0.8, 0.8])
        darker = pal_lab[:, 0] < c[0] - 1e-6
        if darker.any():
            cand = np.nonzero(darker)[0]
            out[i] = palette[cand[np.argmin(np.linalg.norm(pal_lab[cand] - target, axis=1))]]
    sub = region[inside]
    sub[:, :3] = out[inv.reshape(-1)]
    region[inside] = sub


def _paste(canvas: RGBA, img: RGBA, left: int, top: int) -> None:
    h, w = canvas.shape[:2]
    sx0, sy0 = max(0, -left), max(0, -top)
    dx0, dy0 = max(0, left), max(0, top)
    dx1, dy1 = min(w, left + img.shape[1]), min(h, top + img.shape[0])
    if dx0 >= dx1 or dy0 >= dy1:
        return
    src = img[sy0 : sy0 + dy1 - dy0, sx0 : sx0 + dx1 - dx0]
    mask = src[..., 3] > 127  # pixel art keeps hard edges: a pixel is in or out
    canvas[dy0:dy1, dx0:dx1][mask] = src[mask]


def compose(
    scene: Scene, project: Project, *, states: dict[str, str] | None = None, frame: int = 0,
    shadows: bool = True,
) -> Composed:  # fmt: skip
    states = states or {}
    for name in states:
        scene.layer(name)  # unknown layer names fail early
    canvas = background_image(scene, project)
    pieces: list[tuple[Layer, str, RGBA, str, int]] = []
    warnings: list[str] = []
    longest = 1
    for layer in sorted(scene.layers, key=lambda la: la.order):
        state = states.get(layer.name, layer.state)
        if layer.sizes:
            ref, img, warn = _pick_size(scene, project, layer)
            warnings += warn
        else:
            if state != "default" and state not in layer.states:
                raise SceneError(f"{layer.name}: no state {state!r} (has {sorted(layer.states)})")
            ref = layer.states.get(state) or layer.asset or ""
            img = asset_image(project, ref)
        n = layer.frames.get(state, 1)
        if n > 1:
            img = frame_of(img, n, frame)
            longest = max(longest, n)
        pieces.append((layer, ref, img, state, n))
    seen = [canvas[canvas[..., 3] > 0][:, :3]] + [p[2][p[2][..., 3] > 127][:, :3] for p in pieces]
    palette = np.unique(np.concatenate(seen), axis=0)
    placed: list[Placed] = []
    for layer, ref, img, state, n in pieces:
        left_box, _, right_box, bottom = opaque_box(img)
        x, y = layer.at
        left = x - (left_box + right_box) // 2
        top = y - bottom
        if shadows and layer.shadow and layer.z is None:
            _shadow(canvas, x, y - 1, max(2.0, (right_box - left_box) * 0.6), scene, palette)
        _paste(canvas, img, left, top)
        placed.append(Placed(layer.name, ref, left, top, img.shape[1], img.shape[0], state,
                             frame % n, n))  # fmt: skip
    return Composed(canvas, placed, warnings, longest)


def layout(scene: Scene, out: Composed) -> dict[str, Any]:
    """Where everything went, for a game engine."""
    return {
        **scene.to_dict(),
        "layers": [p.__dict__ for p in out.placed],
    }


def write_outputs(
    scene: Scene, project: Project, out: Composed, *, viewport_x: int | None = None,
    gif: bool = False, states: dict[str, str] | None = None,
) -> list[Path]:  # fmt: skip
    folder = project.export_dir / SCENES_DIR
    folder.mkdir(parents=True, exist_ok=True)

    def view(img: RGBA) -> Image.Image:
        if viewport_x is not None:
            vw = scene.viewport[0]
            x = max(0, min(viewport_x, img.shape[1] - vw))
            img = img[:, x : x + vw]
        return Image.fromarray(img, "RGBA")

    png = folder / f"{scene.name}.png"
    view(out.image).save(png)
    data = folder / f"{scene.name}.json"
    data.write_text(json.dumps(layout(scene, out), indent=2) + "\n", encoding="utf-8")
    paths = [png, data]
    if gif and out.frames > 1:
        frames = [view(compose(scene, project, states=states, frame=i).image)
                  for i in range(out.frames)]  # fmt: skip
        anim = folder / f"{scene.name}.gif"
        frames[0].save(anim, save_all=True, append_images=frames[1:], duration=FRAME_MS,
                       loop=0, disposal=2)  # fmt: skip
        paths.append(anim)
    return paths


# --- sizes and prompts ------------------------------------------------------------------


def suggested_sizes(
    scene: Scene, near_y: float | None = None, far_y: float | None = None
) -> list[int]:
    """Character heights to draw so every depth from `far_y` to `near_y` is within reach."""
    near = scene.person_height(near_y if near_y is not None else scene.viewport[1])
    far = scene.person_height(
        far_y if far_y is not None else scene.horizon + 0.3 * (scene.viewport[1] - scene.horizon)
    )
    sizes = [round(near)]
    while sizes[-1] * SIZE_STEP > far * (1 - SIZE_TOLERANCE):
        sizes.append(round(sizes[-1] * SIZE_STEP))
    return sizes


def size_prompt(height: int, largest: int) -> str:
    if height >= largest:
        return f"The figure fills the frame, {height} px tall from head to feet."
    return (
        f"A simplified redraw of the same character, {height} px tall from head to feet, "
        "filling the frame: fewer details, the same silhouette, colours and outline."
    )


def scene_prompt(scene: Scene, at_y: float, height: float | None = None) -> str:
    """Words that make a prop or character match the scene's camera, horizon and scale."""
    person = scene.person_height(at_y)
    tall = height if height is not None else person
    eye = (at_y - scene.horizon) / tall  # where the eye level crosses the object, from its base
    if eye >= 1.05:
        view = "The camera looks slightly down on it: its top surface shows a little."
    elif eye <= 0.05:
        view = "The camera is at floor level: its top is not visible, it looms upward."
    else:
        view = (
            f"The eye level crosses it at {round(eye * 100)}% of its height: "
            "neither its top nor its underside shows."
        )
    parts = [CAMERA_WORDS[scene.camera], view]
    if height is not None:
        parts.append(
            f"About {round(height)} px tall; a person beside it would be {round(person)} px."
        )
    else:
        parts.append(f"The figure is {round(person)} px tall from head to feet.")
    parts.append("On a flat background, no floor, no cast shadow.")
    return " ".join(parts)
