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
import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageDraw

from pixelwright.asset import FINAL, Asset, AssetError
from pixelwright.core.color import srgb8_to_oklab
from pixelwright.core.seam import join
from pixelwright.project import Project

SCENES_DIR = "scenes"
PERSON_M = 1.75  # a person's height in metres, to state the camera height
CAMERA_M = (0.6, 4.0)  # camera heights (m) outside this range mean horizon and scale disagree
FOV_DEG = 50.0  # assumed vertical field of view, to turn rows into angles
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
    floor: list[tuple[int, int]] = field(default_factory=list)  # walkable polygon, optional

    @property
    def camera_height(self) -> float:
        """Camera height in metres that the horizon and the scale reference imply."""
        return PERSON_M * (self.ref_y - self.horizon) / self.ref_height

    def on_floor(self, x: float, y: float) -> bool:
        """Whether (x, y) lies on the walkable floor (anything below the horizon if unset)."""
        if not self.floor:
            return y > self.horizon
        inside = False
        pts = self.floor
        for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1], strict=True):
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
        return inside

    def checks(self) -> list[str]:
        """Disagreements between the horizon and the scale reference."""
        h = self.camera_height
        if CAMERA_M[0] <= h <= CAMERA_M[1]:
            return []
        return [
            f"horizon {self.horizon:g} and the scale reference put the camera {h:.1f} m above "
            "the floor: one of them is off (pw scene analyze estimates the horizon)"
        ]

    def person_height(self, y: float) -> float:
        """Height in px of a person whose feet are at row `y`."""
        return self.ref_height * (y - self.horizon) / (self.ref_y - self.horizon)

    def layers_in_order(self) -> list[Layer]:
        """Far to near by base row; `z` overrides."""
        return sorted(self.layers, key=lambda la: la.order)

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
            "camera_height_m": round(self.camera_height, 2),
            "floor": [list(p) for p in self.floor],
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
        p = _table(raw["person"], f"{where}.person")
        return _num(p.get("y"), f"{where}.person.y"), _num(p.get("height"), f"{where}.person")
    if "door" in raw:
        d = _table(raw["door"], f"{where}.door")
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
    raw_frames = _table(raw.get("frames", {}), f"{where}.frames").items()
    frames = {str(k): int(_num(v, f"{where}.frames")) for k, v in raw_frames}
    if any(n < 1 for n in frames.values()):
        raise SceneError(f"{where} ({name}): frames must be at least 1")
    return Layer(
        name=name,
        at=_pair(raw.get("at"), f"{where} ({name}).at"),
        asset=str(asset) if asset else None,
        sizes=sizes,
        states={str(k): str(v) for k, v in _table(raw.get("states", {}), where).items()},
        frames=frames,
        state=str(raw.get("state", "default")),
        z=_num(raw["z"], f"{where}.z") if "z" in raw else None,
        shadow=bool(raw.get("shadow", True)),
    )


def parse_scene(raw: dict[str, Any], name: str, path: Path, canvas: tuple[int, int]) -> Scene:
    head = _table(raw.get("scene", {}), "scene")
    viewport = _pair(head["viewport"], "scene.viewport") if "viewport" in head else canvas
    if "horizon" not in head:
        raise SceneError(f"{path}: [scene] needs horizon = <row>")
    horizon = _num(head["horizon"], "scene.horizon")
    camera = str(head.get("camera", "frontal"))
    if camera not in CAMERAS:
        raise SceneError(f"{path}: camera must be one of {', '.join(CAMERAS)}")
    ref_y, ref_h = _scale(_table(head.get("scale", {}), "scene.scale"), "scene.scale")
    if ref_y <= horizon or ref_h <= 0:
        raise SceneError(f"{path}: the scale reference must stand below the horizon")
    backgrounds = []
    for i, item in enumerate(raw.get("background", [])):
        b = _table(item, f"background[{i}]")
        if not b.get("asset"):
            raise SceneError(f"{path}: background[{i}] needs an asset")
        x = int(_num(b.get("x", 0), f"background[{i}].x"))
        if x < 0:
            raise SceneError(f"{path}: background[{i}].x must be 0 or more")
        backgrounds.append((str(b["asset"]), x))
    if not backgrounds:
        raise SceneError(f"{path}: add a [[background]] with an asset")
    backgrounds.sort(key=lambda b: b[1])
    raw_layers = raw.get("layer", [])
    layers = [_layer(_table(r, f"layer[{i}]"), f"layer[{i}]") for i, r in enumerate(raw_layers)]
    names = [layer.name for layer in layers]
    if len(set(names)) != len(names):
        raise SceneError(f"{path}: layer names must be unique")
    width = int(_num(head.get("width", viewport[0]), "scene.width"))
    raw_floor = head.get("floor", [])
    if not isinstance(raw_floor, list):
        raise SceneError(f"{path}: floor must be a list of [x, y] points")
    floor = [_pair(pt, "scene.floor") for pt in raw_floor]
    if floor and len(floor) < 3:
        raise SceneError(f"{path}: floor needs at least 3 points")
    return Scene(
        name, path, viewport, width, horizon, camera, ref_y, ref_h, backgrounds, layers, floor
    )


def _table(raw: object, where: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SceneError(f"{where}: expected a table, got {raw!r}")
    return raw


def load_scene(project: Project, name: str) -> Scene:
    path = scene_path(project, name)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SceneError(f"no scene {name!r} (looked for {path})") from exc
    except tomllib.TOMLDecodeError as exc:
        raise SceneError(f"{path}: {exc}") from exc
    canvas = (project.canvas["width"], project.canvas["height"])
    try:
        return parse_scene(raw, name, path, canvas)
    except (KeyError, AttributeError, TypeError) as exc:
        raise SceneError(f"{path}: malformed scene ({exc})") from exc


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
    text = TEMPLATE.format(
        name=name, horizon=horizon, camera=camera, door_y=door_y, door_h=door_h,
        background=background,
    )  # fmt: skip
    canvas = (project.canvas["width"], project.canvas["height"])
    parse_scene(tomllib.loads(text), name, path, canvas)  # validate before writing
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
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
        if overlap > tile.shape[1]:
            raise SceneError(f"{ref}: tile at x={x} ends inside the tile before it")
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


def _shadow(
    canvas: RGBA, floor: npt.NDArray[np.bool_], cx: int, cy: int, half_w: float, scene: Scene,
    palette: RGBA,
) -> None:  # fmt: skip
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
    inside &= (region[..., 3] > 0) & floor[y0:y1, x0:x1]  # only floor: never a layer
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


def _paste(canvas: RGBA, floor: npt.NDArray[np.bool_], img: RGBA, left: int, top: int) -> None:
    h, w = canvas.shape[:2]
    sx0, sy0 = max(0, -left), max(0, -top)
    dx0, dy0 = max(0, left), max(0, top)
    dx1, dy1 = min(w, left + img.shape[1]), min(h, top + img.shape[0])
    if dx0 >= dx1 or dy0 >= dy1:
        return
    src = img[sy0 : sy0 + dy1 - dy0, sx0 : sx0 + dx1 - dx0]
    mask = src[..., 3] > 127  # pixel art keeps hard edges: a pixel is in or out
    canvas[dy0:dy1, dx0:dx1][mask] = src[mask]
    floor[dy0:dy1, dx0:dx1][mask] = False


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
    for layer in scene.layers_in_order():
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
    palette = np.unique(canvas[canvas[..., 3] > 0][:, :3], axis=0)  # the floor's own colours
    placed: list[Placed] = []
    floor = np.ones(canvas.shape[:2], bool)  # pixels no layer has covered yet
    warnings += scene.checks()
    for layer, ref, img, state, n in pieces:
        left_box, _, right_box, bottom = opaque_box(img)
        x, y = layer.at
        if layer.z is None and not scene.on_floor(x, y):
            warnings.append(f"{layer.name}: its base ({x}, {y}) is off the floor, it will float")
        left = x - (left_box + right_box) // 2
        top = y - bottom
        if shadows and layer.shadow and layer.z is None:
            _shadow(canvas, floor, x, y - 1, max(2.0, (right_box - left_box) * 0.6), scene, palette)
        _paste(canvas, floor, img, left, top)
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
    gif: bool = False, states: dict[str, str] | None = None, shadows: bool = True,
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
    if gif and out.frames == 1:
        out.warnings.append("no animated state is shown: no GIF written (pick one with --state)")
    if gif and out.frames > 1:
        frames = [view(compose(scene, project, states=states, frame=i, shadows=shadows).image)
                  for i in range(out.frames)]  # fmt: skip
        anim = folder / f"{scene.name}.gif"
        frames[0].save(anim, save_all=True, append_images=frames[1:], duration=FRAME_MS,
                       loop=0, disposal=2)  # fmt: skip
        paths.append(anim)
    return paths


def set_horizon(scene: Scene, row: int) -> None:
    """Rewrite the `horizon = ...` line of the scene file, keeping everything else."""
    lines = scene.path.read_text(encoding="utf-8").splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.split("=")[0].strip() == "horizon":
            comment = line[line.index("#") :] if "#" in line else "\n"
            lines[i] = f"horizon = {row}" + (f"  {comment}" if "#" in line else comment)
            break
    else:
        raise SceneError(f"{scene.path}: no horizon line to update")
    scene.path.write_text("".join(lines), encoding="utf-8")


# --- perspective --------------------------------------------------------------------------

VP_EDGE_SHARE = 0.15  # strongest edges used to find the vanishing point
VP_NEAR = 0.12  # edges closer than this share of the width to a candidate do not vote for it


def vanishing_point(img: RGBA) -> tuple[int, int, float]:
    """The point where the image's receding lines meet: (x, y, share of edge weight agreeing).

    Each strong edge pixel defines a line (perpendicular to its gradient); the candidate
    that most of those lines pass through wins. Horizontal and vertical edges are left out:
    in a frontal room they never recede. The vanishing point's row is the horizon.
    """
    rgb = img[..., :3].astype(float)
    lum = rgb @ np.array([0.299, 0.587, 0.114])
    if img.shape[-1] == 4:
        lum[img[..., 3] == 0] = 0.0
    h, w = lum.shape
    for _ in range(2):  # soften pixel stair-steps so edge directions follow the line
        pad = np.pad(lum, 1, mode="edge")
        lum = sum(pad[dy : dy + h, dx : dx + w] for dy in range(3) for dx in range(3)) / 9.0
    gx = np.zeros_like(lum)
    gy = np.zeros_like(lum)
    c = lum
    right = c[:-2, 2:] + 2 * c[1:-1, 2:] + c[2:, 2:]
    left = c[:-2, :-2] + 2 * c[1:-1, :-2] + c[2:, :-2]
    below = c[2:, :-2] + 2 * c[2:, 1:-1] + c[2:, 2:]
    above = c[:-2, :-2] + 2 * c[:-2, 1:-1] + c[:-2, 2:]
    gx[1:-1, 1:-1] = right - left
    gy[1:-1, 1:-1] = below - above
    mag = np.hypot(gx, gy)
    if not mag.any():
        raise SceneError("no edges to find a vanishing point in")
    ys, xs = np.nonzero(mag >= np.quantile(mag[mag > 0], 1 - VP_EDGE_SHARE))
    nx, ny = gx[ys, xs] / mag[ys, xs], gy[ys, xs] / mag[ys, xs]
    ang = np.degrees(np.arctan2(nx, -ny)) % 180  # direction of the edge line
    keep = (np.abs(ang - 90) > 12) & (np.minimum(ang, 180 - ang) > 8)
    if keep.sum() < 20:
        raise SceneError("too few receding lines to find a vanishing point")
    xs, ys, nx, ny = xs[keep], ys[keep], nx[keep], ny[keep]
    wt = mag[ys, xs]
    near = VP_NEAR * w

    def score(cx: int, cy: int) -> float:
        dist = np.abs((cx - xs) * nx + (cy - ys) * ny)
        return float(wt[(dist < 1.5) & (np.hypot(cx - xs, cy - ys) > near)].sum())

    coarse = max((score(cx, cy), cx, cy) for cy in range(0, h, 3) for cx in range(0, w, 4))
    _, x0, y0 = coarse
    best = max(
        (score(cx, cy), cx, cy)
        for cy in range(max(0, y0 - 3), min(h, y0 + 4))
        for cx in range(max(0, x0 - 4), min(w, x0 + 5))
    )
    return best[1], best[2], best[0] / float(wt.sum())


def guides(scene: Scene, out: Composed) -> RGBA:
    """The composed scene with the horizon, the floor outline and each layer's base marked."""
    im = Image.fromarray(out.image, "RGBA").convert("RGB")
    draw = ImageDraw.Draw(im)
    draw.line([(0, scene.horizon), (im.width, scene.horizon)], fill=(0, 255, 0))
    if scene.floor:
        draw.line([*scene.floor, scene.floor[0]], fill=(255, 220, 0))
    for layer in scene.layers:
        x, y = layer.at
        colour = (0, 255, 255) if scene.on_floor(x, y) else (255, 0, 0)
        draw.line([(x - 3, y), (x + 3, y)], fill=colour)
        draw.line([(x, y - 3), (x, y)], fill=colour)
    return np.asarray(im.convert("RGBA")).copy()


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
    if at_y <= scene.horizon:
        raise SceneError(f"row {at_y:g} is at or above the horizon ({scene.horizon:g})")
    if height is not None and height <= 0:
        raise SceneError("height must be more than 0")
    person = scene.person_height(at_y)
    tall = height if height is not None else person
    eye = (at_y - scene.horizon) / tall  # where the eye level crosses the object, from its base
    focal = scene.viewport[1] / (2 * math.tan(math.radians(FOV_DEG / 2)))
    down = math.degrees(math.atan((at_y - tall / 2 - scene.horizon) / focal))
    if eye >= 1.05:
        how = "slightly" if down < 8 else "clearly"
        view = (
            f"The camera looks {how} down on it, about {round(down)} degrees from above: "
            "its top surface shows a little."
        )
    elif eye <= 0.05:
        view = "The camera is at floor level: its top is not visible, it looms upward."
    else:
        view = (
            f"Straight side-on, at eye level: the eye level crosses it at {round(eye * 100)}% "
            "of its height, so neither its top nor its underside shows."
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
