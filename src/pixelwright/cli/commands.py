"""Command handlers. Each takes the workspace root and parsed arguments, returns an Outcome."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from pixelwright.cli.registry import EXIT_CHECK, Outcome, Param, PwError, command
from pixelwright.core import checks as C
from pixelwright.core.clean import clean
from pixelwright.core.image import Image, IndexedImage, RGBImage
from pixelwright.core.palette import Palette, Ramps
from pixelwright.core.quantize import discover_palette, quantize_fixed
from pixelwright.core.render import grayscale, overlay, upscale, value_map
from pixelwright.core.snap import snap
from pixelwright.io.aseprite import flatten_frames, read_aseprite
from pixelwright.io.palette_io import read_palette, write_palette
from pixelwright.io.png import encode_png, read_png, write_png
from pixelwright.workspace import Asset, Workspace, WorkspaceConfig
from pixelwright.workspace.asset import KINDS
from pixelwright.workspace.files import sha256_bytes, write_bytes_atomic
from pixelwright.workspace.style import bump_style, load_ramps

Mask = npt.NDArray[np.bool_]
IMAGE = "image.png"
VIEWS = ("upscale", "gray", "values", "silhouette", "overlay", "gif", "apng")

ASSET = Param("asset", help="asset id", required=True, positional=True)
VERSION = Param("version", help="version (default: latest)")
MASK = Param("mask", help="mask id from the asset's masks/")


# -- helpers ------------------------------------------------------------------
def _rel(ws: Workspace, path: Path) -> str:
    return path.relative_to(ws.root).as_posix()


def _version(asset: Asset, version: str | None) -> str:
    found = version or asset.latest()
    if found is None:
        raise PwError("no_versions", f"asset {asset.id} has no versions; run `pw attach`")
    if found not in asset.versions():
        raise PwError("version_not_found", f"{asset.id} has no version {found}")
    return found


def _image(asset: Asset, version: str) -> Image:
    return read_png(asset.versions_dir / version / IMAGE)


def _indexed(image: Image, step: str) -> IndexedImage:
    if not isinstance(image, IndexedImage):
        raise PwError("not_indexed", f"{step} needs an indexed image; run `pw quantize` first")
    return image


def _publish(
    ws: Workspace, asset: Asset, step: str, image: Image, parent: str | None, **params: Any
) -> Outcome:
    data = encode_png(image)
    version = asset.new_version(step, {IMAGE: data}, params=params, parent=parent)
    path = asset.versions_dir / version / IMAGE
    return Outcome(asset.id, version, asset.stage(version), [_rel(ws, path)])


def _style_file(ws: Workspace, ref: str) -> Path:
    path = ws.path("style") / ref.removeprefix("style:")
    if not path.is_file():
        raise PwError("not_found", f"no such style file: {ref}")
    return path


def _asset_palette(ws: Workspace, asset: Asset, override: str | None) -> Palette | None:
    ref = override or asset.spec().get("palette")
    return read_palette(_style_file(ws, str(ref))) if ref else None


def _mask(asset: Asset, mask_id: str | None, shape: tuple[int, int]) -> Mask | None:
    if mask_id is None:
        return None
    entry = next((m for m in asset.masks() if m["id"] == mask_id), None)
    if entry is None:
        raise PwError("mask_not_found", f"{asset.id} has no mask {mask_id}")
    return region_mask(asset, entry, shape)


def region_mask(asset: Asset, entry: dict[str, Any], shape: tuple[int, int]) -> Mask:
    """The boolean region of an issue: its mask PNG, its box, or the whole image."""
    region = entry.get("region", "mask")
    if region == "image":
        return np.ones(shape, dtype=bool)
    if region == "box":
        x, y, w, h = entry["box"]
        on: Mask = np.zeros(shape, dtype=bool)
        on[y : y + h, x : x + w] = True
        return on
    rgba = read_png(asset.path / entry["file"]).to_rgba()
    if rgba.shape[:2] != shape:
        raise PwError("mask_shape", f"mask {entry['id']} is {rgba.shape[1]}x{rgba.shape[0]}")
    drawn: Mask = (rgba[..., 3] > 0) & (rgba[..., :3].max(axis=-1) >= 128)
    return drawn


def _canvas(text: str) -> dict[str, int]:
    w, sep, h = text.lower().partition("x")
    if not sep or not w.isdigit() or not h.isdigit() or int(w) < 1 or int(h) < 1:
        raise PwError("invalid", f"canvas must be WIDTHxHEIGHT, got {text!r}")
    return {"width": int(w), "height": int(h)}


def _register_palette(ws: Workspace, path: Path, note: str) -> str:
    rel = _rel_style(ws, path)
    guide = ws.style()
    if rel not in guide.palettes:
        bump_style(ws.path("style"), {"palettes": [*guide.palettes, rel]}, note=note)
    return rel


def _rel_style(ws: Workspace, path: Path) -> str:
    return path.relative_to(ws.path("style")).as_posix()


# -- workspace and assets -----------------------------------------------------
@command(
    "init",
    "create a workspace (pixelwright.toml, style/, assets/...)",
    Param("path", help="workspace folder (same as --workspace)", positional=True),
    Param("canvas", help="default canvas WIDTHxHEIGHT"),
    needs_workspace=False,
)
def cmd_init(root: Path, a: dict[str, Any]) -> Outcome:
    if a["path"]:
        root = Path(a["path"])
    config = WorkspaceConfig()
    if a["canvas"]:
        config.canvas = _canvas(a["canvas"])
    ws = Workspace.init(root, config)
    return Outcome(data={"root": str(ws.root), "roles": ws.config.roles})


@command(
    "new",
    "create an asset",
    ASSET,
    Param("kind", help="asset kind", required=True, choices=KINDS),
    Param("canvas", help="canvas WIDTHxHEIGHT (default: workspace canvas)"),
    Param("palette", help="palette file under style/, e.g. palettes/scene.gpl"),
)
def cmd_new(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    fields: dict[str, Any] = {}
    if a["palette"]:
        fields["palette"] = "style:" + _rel_style(ws, _style_file(ws, a["palette"]))
    canvas = _canvas(a["canvas"]) if a["canvas"] else None
    asset = ws.new_asset(a["asset"], a["kind"], canvas=canvas, **fields)
    return Outcome(asset.id, stage="draft", outputs=[_rel(ws, asset.spec_path)], data=asset.spec())


@command(
    "attach",
    "add an image: as a new source version, a sketch or a reference",
    ASSET,
    Param("file", help="image file", required=True, positional=True),
    Param("as", help="what the file is", default="source", choices=("source", "sketch", "ref")),
    Param("parent", help="version the file was edited from (source only)"),
    Param("note", help="history note, e.g. what was retouched", default=""),
    Param("author", help="who made it", default="human", choices=("human", "claude")),
)
def cmd_attach(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    asset = ws.asset(a["asset"])
    src = Path(a["file"])
    if not src.is_file():
        raise PwError("not_found", f"no such file: {src}")
    if a["as"] == "source":
        image = read_png(src)
        parent = _version(asset, a["parent"]) if a["parent"] else None
        outcome = _publish(ws, asset, "attach", image, parent, file=src.name)
        outcome.data = {"width": image.width, "height": image.height}
    else:
        raw = src.read_bytes()
        folder = asset.path / "inputs"
        dest = folder / (f"sketch{src.suffix}" if a["as"] == "sketch" else f"refs/{src.name}")
        write_bytes_atomic(dest, raw)
        outcome = Outcome(asset.id, outputs=[_rel(ws, dest)], data={"sha256": sha256_bytes(raw)})
    if a["note"]:
        asset.note(a["note"], author=a["author"], version=outcome.version)
    return outcome


# -- pipeline steps -----------------------------------------------------------
@command(
    "snap",
    "detect the pixel grid and downsample to native resolution",
    ASSET,
    VERSION,
    Param("scale", "int", help="force this scale instead of detecting it"),
)
def cmd_snap(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    asset = ws.asset(a["asset"])
    parent = _version(asset, a["version"])
    image = _image(asset, parent)
    rgb = image if isinstance(image, RGBImage) else image.to_rgb_image()
    result = snap(rgb, scale=a["scale"])
    outcome = _publish(ws, asset, "snap", result.image, parent, scale=result.scale)
    outcome.data = {
        "scale": result.scale,
        "offset": list(result.offset),
        "confidence": result.confidence,
    }
    if result.confidence < 0.5:
        outcome.warnings.append(f"low snap confidence {result.confidence:.2f}; check the scale")
    return outcome


@command(
    "quantize",
    "map onto the asset palette (or discover one); dither only inside a mask",
    ASSET,
    VERSION,
    Param("palette", help="palette file under style/ (default: the asset palette)"),
    Param("discover", "int", help="discover a palette of this many colors instead"),
    Param("dither_mask", help="mask id where Bayer dithering is allowed"),
)
def cmd_quantize(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    asset = ws.asset(a["asset"])
    parent = _version(asset, a["version"])
    image = _image(asset, parent)
    rgb = image if isinstance(image, RGBImage) else image.to_rgb_image()
    if a["discover"]:
        palette: Palette | None = discover_palette(rgb, a["discover"])
    else:
        palette = _asset_palette(ws, asset, a["palette"])
    if palette is None:
        raise PwError("no_palette", "no palette: pass --palette, --discover or set one on `new`")
    dither = _mask(asset, a["dither_mask"], (rgb.height, rgb.width))
    indexed, report = quantize_fixed(rgb, palette, dither_mask=dither)
    params = {k: a[k] for k in ("palette", "discover", "dither_mask") if a[k]}
    outcome = _publish(ws, asset, "quantize", indexed, parent, **params)
    outcome.data = {**asdict(report), "colors": len(palette)}
    return outcome


@command(
    "clean",
    "remove orphan pixels (and isolated pairs), optionally inside a mask",
    ASSET,
    VERSION,
    MASK,
    Param("pairs", "bool", help="also remove isolated two-pixel clusters"),
)
def cmd_clean(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    asset = ws.asset(a["asset"])
    parent = _version(asset, a["version"])
    image = _indexed(_image(asset, parent), "clean")
    region = _mask(asset, a["mask"], image.indices.shape)
    cleaned, report = clean(image, region, pairs=a["pairs"])
    params = {k: a[k] for k in ("mask", "pairs") if a[k]}
    outcome = _publish(ws, asset, "clean", cleaned, parent, **params)
    outcome.data = asdict(report)
    return outcome


# -- checks -------------------------------------------------------------------
@dataclass
class _CheckInput:
    image: Image
    indexed: IndexedImage | None
    palette: Palette | None
    ramps: Ramps | None
    mask: Mask | None
    layers: list[Mask]
    light: tuple[float, float]
    export: Image | None = None
    scale: int = 1


class _Missing(Exception):
    """A check's input is not available; the check is skipped with a warning."""


def _need(value: object, what: str) -> None:
    if value is None or (isinstance(value, list) and not value):
        raise _Missing(what)


def _ix(i: _CheckInput) -> IndexedImage:
    _need(i.indexed, "an indexed image")
    assert i.indexed is not None
    return i.indexed


def _pal(i: _CheckInput) -> Palette:
    _need(i.palette, "a palette")
    assert i.palette is not None
    return i.palette


def _msk(i: _CheckInput) -> Mask:
    _need(i.mask, "--mask")
    assert i.mask is not None
    return i.mask


def _ramps(i: _CheckInput) -> C.CheckResult:
    _need(i.ramps, "style ramps")
    assert i.ramps is not None
    return C.check_ramps(_pal(i), i.ramps)


def _grid(i: _CheckInput) -> C.CheckResult:
    _need(i.export, "--file (an upscaled export) and --scale")
    assert i.export is not None
    return C.check_grid(i.export, i.scale)


def _depth(i: _CheckInput) -> C.CheckResult:
    _need(i.layers, "--layers")
    return C.check_depth_falloff(i.image, i.layers)


CHECKS: dict[str, Callable[[_CheckInput], C.CheckResult]] = {
    "palette": lambda i: C.check_palette(i.image, _pal(i)),
    "grid": _grid,
    "orphans": lambda i: C.check_orphans(_ix(i)),
    "value-groups": lambda i: C.check_value_groups(i.image),
    "focal-contrast": lambda i: C.check_focal_contrast(i.image, _msk(i)),
    "line-runs": lambda i: C.check_line_runs(_ix(i)),
    "banding": lambda i: C.check_banding(_ix(i)),
    "pillow": lambda i: C.check_pillow(i.image, i.light),
    "ramps": _ramps,
    "dither-zones": lambda i: C.check_dither_zones(_ix(i), i.mask),
    "aa": lambda i: C.check_aa(_ix(i)),
    "selout": lambda i: C.check_selout(i.image),
    "outline-share": lambda i: C.check_outline_share(_ix(i)),
    "depth-falloff": _depth,
    "figure-ground": lambda i: C.check_figure_ground(i.image, _msk(i)),
    "diagnostics": lambda i: C.check_diagnostics(i.image, i.mask),
}


@command(
    "check",
    "run detectors and write report.json next to the version",
    ASSET,
    VERSION,
    Param("checks", "list", help="checks to run (default: all that apply)", choices=tuple(CHECKS)),
    Param("mask", help="mask id: focal area, sprite or dither zones"),
    Param("layers", "list", help="mask ids, near to far, for depth-falloff"),
    Param("file", help="upscaled export PNG for the grid check"),
    Param("scale", "int", help="upscale factor of --file for the grid check", default=1),
)
def cmd_check(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    asset = ws.asset(a["asset"])
    version = _version(asset, a["version"])
    image = _image(asset, version)
    shape = (image.height, image.width)
    guide = ws.style()
    palette = _asset_palette(ws, asset, None)
    if palette is None and isinstance(image, IndexedImage):
        palette = image.palette
    direction = guide.light.get("direction", (-0.6, -0.8))
    inputs = _CheckInput(
        image=image,
        indexed=image if isinstance(image, IndexedImage) else None,
        palette=palette,
        ramps=load_ramps(ws.path("style"), guide),
        mask=_mask(asset, a["mask"], shape),
        layers=[m for m in (_mask(asset, x, shape) for x in a["layers"] or []) if m is not None],
        light=(float(direction[0]), float(direction[1])),
        export=read_png(Path(a["file"])) if a["file"] else None,
        scale=a["scale"],
    )
    results, warnings = [], []
    for name in a["checks"] or CHECKS:
        try:
            results.append(CHECKS[name](inputs))
        except _Missing as missing:
            warnings.append(f"skipped {name}: needs {missing}")
    report = asset.versions_dir / version / "report.json"
    C.write_report(report, results)
    summary = [{"check": r.check, "status": r.status, "value": r.value} for r in results]
    flagged = sum(r.flagged for r in results)
    data = {"results": summary, "flagged": flagged}
    return Outcome(asset.id, version, asset.stage(version), [_rel(ws, report)], data, warnings)


# -- views --------------------------------------------------------------------
def _report_mask(asset: Asset, version: str, shape: tuple[int, int]) -> Mask:
    mask = np.zeros(shape, dtype=bool)
    path = asset.versions_dir / version / "report.json"
    if path.exists():
        for result in C.read_report(path):
            for region in result["regions"]:
                if "box" in region:
                    x, y, w, h = region["box"]
                    mask[y : y + h, x : x + w] = True
    return mask


@command(
    "render",
    "write a review view (integer upscale of the image, gray, values, silhouette, overlay)",
    ASSET,
    VERSION,
    Param("view", help="what to render", default="upscale", choices=VIEWS),
    Param("scale", "int", help="integer upscale factor", default=4),
    Param("mask", help="mask id to overlay (default: the report's flagged regions)"),
)
def cmd_render(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    asset = ws.asset(a["asset"])
    version = _version(asset, a["version"])
    view = a["view"]
    if view in ("gif", "apng"):
        return _render_animation(ws, asset, version, view, a["scale"])
    image = _image(asset, version)
    rgba = image.to_rgba()
    if view == "gray":
        rgba = grayscale(rgba)
    elif view == "values":
        rgba = value_map(rgba)
    elif view == "silhouette":
        rgba = np.where(rgba[..., 3:] > 0, np.array([0, 0, 0, 255], np.uint8), 0).astype(np.uint8)
    elif view == "overlay":
        shape = (image.height, image.width)
        mask = _mask(asset, a["mask"], shape)
        rgba = overlay(rgba, mask if mask is not None else _report_mask(asset, version, shape))
    out = ws.path("cache") / "renders" / asset.id / f"{version}-{view}.png"
    write_png(out, RGBImage(upscale(rgba, a["scale"])))
    source = _rel(ws, asset.versions_dir / version / IMAGE)
    data = {"view": view, "source": source}
    return Outcome(asset.id, version, asset.stage(version), [_rel(ws, out)], data)


def _render_animation(ws: Workspace, asset: Asset, version: str, view: str, scale: int) -> Outcome:
    """GIF or APNG of the version's frames (from image.aseprite, else the single PNG)."""
    from PIL import Image as PILImage

    ase = asset.versions_dir / version / "image.aseprite"
    if ase.exists():
        frames = flatten_frames(read_aseprite(ase))
    else:
        frames = [(_image(asset, version).to_rgba(), 100)]
    pics = [PILImage.fromarray(upscale(rgba, scale), "RGBA") for rgba, _ in frames]
    durations = [ms for _, ms in frames]
    ext = "gif" if view == "gif" else "png"
    out = ws.path("cache") / "renders" / asset.id / f"{version}-anim.{ext}"
    out.parent.mkdir(parents=True, exist_ok=True)
    extra: dict[str, Any] = {"disposal": 2} if view == "gif" else {"default_image": False}
    pics[0].save(
        out,
        format="GIF" if view == "gif" else "PNG",
        save_all=True,
        append_images=pics[1:],
        duration=durations,
        loop=0,
        **extra,
    )
    data = {"view": view, "frames": len(frames), "durations": durations}
    return Outcome(asset.id, version, asset.stage(version), [_rel(ws, out)], data)


@command(
    "diff",
    "compare two versions pixel by pixel",
    ASSET,
    Param("version_a", help="first version", required=True, positional=True),
    Param("version_b", help="second version", required=True, positional=True),
)
def cmd_diff(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    asset = ws.asset(a["asset"])
    va, vb = _version(asset, a["version_a"]), _version(asset, a["version_b"])
    ra, rb = _image(asset, va).to_rgba(), _image(asset, vb).to_rgba()
    if ra.shape != rb.shape:
        raise PwError("size_mismatch", f"{va} and {vb} have different sizes")
    changed: Mask = (ra != rb).any(axis=-1)
    ys, xs = np.nonzero(changed)
    bbox = (
        [int(xs.min()), int(ys.min()), int(np.ptp(xs)) + 1, int(np.ptp(ys)) + 1] if xs.size else []
    )
    out = ws.path("cache") / "renders" / asset.id / f"diff-{va}-{vb}.png"
    write_png(out, RGBImage(upscale(overlay(rb, changed), 4)))
    data = {
        "changed": int(changed.sum()),
        "share": float(changed.mean()),
        "bbox": bbox,
        "colors": [_colors_used(ra), _colors_used(rb)],
        "checks": _check_deltas(asset, va, vb),
    }
    return Outcome(asset.id, vb, asset.stage(vb), [_rel(ws, out)], data)


def _colors_used(rgba: npt.NDArray[np.uint8]) -> int:
    opaque = rgba[rgba[..., 3] > 0]
    return int(np.unique(opaque.reshape(-1, 4), axis=0).shape[0]) if opaque.size else 0


def _check_deltas(asset: Asset, va: str, vb: str) -> list[dict[str, Any]]:
    """Per check: status and value in A and in B, from each version's report.json."""

    def results(version: str) -> dict[str, dict[str, Any]]:
        path = asset.versions_dir / version / "report.json"
        return {r["check"]: r for r in C.read_report(path)} if path.exists() else {}

    ra, rb = results(va), results(vb)
    rows = []
    for name in sorted(ra.keys() | rb.keys()):
        a, b = ra.get(name), rb.get(name)
        rows.append(
            {
                "check": name,
                "a": {"status": a["status"], "value": a["value"]} if a else None,
                "b": {"status": b["status"], "value": b["value"]} if b else None,
            }
        )
    return rows


# -- review -------------------------------------------------------------------
@command(
    "mask",
    "add, list or clear the asset's annotation masks",
    ASSET,
    Param(
        "action",
        help="what to do",
        required=True,
        positional=True,
        choices=("add", "list", "clear"),
    ),
    Param("file", help="mask PNG (white = inside) for add"),
    Param("id", help="mask id for add"),
    Param("rule", help="rule the mask is about, e.g. R-PIX-3"),
    Param("note", help="free text", default=""),
    Param("author", help="who drew it", default="human", choices=("human", "claude")),
)
def cmd_mask(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    asset = ws.asset(a["asset"])
    if a["action"] == "add":
        if not a["file"] or not a["id"]:
            raise PwError("invalid", "mask add needs --file and --id")
        png = Path(a["file"]).read_bytes()
        path = asset.add_mask(
            a["id"], png, rule=a["rule"] or "", note=a["note"], author=a["author"]
        )
        return Outcome(asset.id, outputs=[_rel(ws, path)], data={"id": a["id"]})
    if a["action"] == "clear":
        return Outcome(asset.id, data={"removed": asset.clear_masks()})
    return Outcome(asset.id, data={"masks": asset.masks()})


def _decide(root: Path, a: dict[str, Any], decision: str) -> Outcome:
    ws = Workspace.open(root)
    asset = ws.asset(a["asset"])
    version = _version(asset, a["version"])
    asset.decide(version, decision, author=a["author"], note=a["note"])
    ws.refresh_gitignore()
    return Outcome(asset.id, version, asset.stage(version), data={"decision": decision})


_DECISION = (
    ASSET,
    Param("version", help="version to decide on", required=True, positional=True),
    Param("note", help="why", default=""),
    Param("author", help="who decides", default="human", choices=("human", "claude")),
)


@command("approve", "approve a version", *_DECISION)
def cmd_approve(root: Path, a: dict[str, Any]) -> Outcome:
    return _decide(root, a, "approve")


@command("reject", "reject a version", *_DECISION)
def cmd_reject(root: Path, a: dict[str, Any]) -> Outcome:
    return _decide(root, a, "reject")


@command(
    "export",
    "export an approved version to export/ and the mapped game path",
    ASSET,
    Param("version", help="version (default: latest approved)"),
)
def cmd_export(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    asset = ws.asset(a["asset"])
    approved = [v for v in asset.versions() if asset.stage(v) in ("approved", "final")]
    version = a["version"] or (approved[-1] if approved else None)
    if version is None or version not in approved:
        raise PwError("not_approved", f"{asset.id}: export needs an approved version")
    image = _image(asset, version)
    palette = _asset_palette(ws, asset, None)
    if not isinstance(image, IndexedImage) or palette is None:
        raise PwError(
            "check_failed",
            "export needs an indexed image and an asset palette",
            exit_code=EXIT_CHECK,
        )
    result = C.check_palette(image, palette)
    if result.flagged:
        raise PwError(
            "check_failed", "palette check failed", exit_code=EXIT_CHECK, details=result.to_dict()
        )
    data = (asset.versions_dir / version / IMAGE).read_bytes()
    targets = [asset.path / "export" / f"{asset.id}.png"]
    mapped = ws.config.exports.get(str(asset.spec()["kind"]))
    if mapped:
        targets.append(ws.root / mapped / f"{asset.id}.png")
    for target in targets:
        write_bytes_atomic(target, data)
    files = [_rel(ws, t) for t in targets]
    asset.exported(version, files)
    return Outcome(asset.id, version, asset.stage(version), files)


# -- palettes, style, housekeeping -------------------------------------------
@command(
    "palette",
    "import a palette file, discover one from a version, or show the style palettes",
    Param(
        "action",
        help="what to do",
        required=True,
        positional=True,
        choices=("import", "discover", "show"),
    ),
    Param("file", help="palette file (.gpl or .hex) for import"),
    Param("asset", help="asset id for discover"),
    Param("version", help="version for discover (default: latest)"),
    Param("colors", "int", help="number of colors for discover", default=16),
    Param("name", help="file name under style/palettes/ (default: from the source)"),
)
def cmd_palette(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    folder = ws.path("style") / "palettes"
    if a["action"] == "show":
        style_dir = ws.path("style")
        sizes = {rel: len(read_palette(style_dir / rel)) for rel in ws.style().palettes}
        return Outcome(data={"palettes": sizes})
    if a["action"] == "import":
        if not a["file"]:
            raise PwError("invalid", "palette import needs --file")
        src = Path(a["file"])
        palette = read_palette(src)
        dest = folder / (a["name"] or src.name)
    else:
        if not a["asset"]:
            raise PwError("invalid", "palette discover needs --asset")
        asset = ws.asset(a["asset"])
        image = _image(asset, _version(asset, a["version"]))
        rgb = image if isinstance(image, RGBImage) else image.to_rgb_image()
        palette = discover_palette(rgb, a["colors"])
        dest = folder / (a["name"] or f"{asset.id}.gpl")
    write_palette(dest, palette)
    rel = _register_palette(ws, dest, note=f"palette {a['action']}: {dest.name}")
    if a["action"] == "discover" and not ws.asset(a["asset"]).spec().get("palette"):
        ws.asset(a["asset"]).update_spec(palette="style:" + rel)
    return Outcome(outputs=[_rel(ws, dest)], data={"palette": rel, "colors": len(palette)})


@command(
    "style",
    "show the style guide or bump it with changes",
    Param("action", help="what to do", required=True, positional=True, choices=("show", "bump")),
    Param("changes", help='JSON object of fields to change, e.g. {"notes": "..."}'),
    Param("note", help="why", default=""),
)
def cmd_style(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    if a["action"] == "bump":
        try:
            changes = json.loads(a["changes"] or "")
        except json.JSONDecodeError as exc:
            raise PwError("invalid", f"--changes is not JSON: {exc}") from exc
        if not isinstance(changes, dict) or not changes:
            raise PwError("invalid", "--changes must be a non-empty JSON object")
        bump_style(ws.path("style"), changes, note=a["note"])
    guide = ws.style().to_dict()
    stale = [{"asset": s, "style_version": v} for s, v in ws.stale_assets()]
    return Outcome(
        outputs=[_rel(ws, ws.path("style") / "style.yaml")], data={"style": guide, "stale": stale}
    )


@command(
    "prune",
    "delete experiment files",
    Param("stage", help="stage to prune", default="experiment", choices=("experiment",)),
    Param("dry_run", "bool", help="list what would be removed"),
)
def cmd_prune(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    base = ws.path("experiments")
    entries = sorted(base.iterdir()) if base.exists() else []
    if not a["dry_run"]:
        for entry in entries:
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink()
    removed = [_rel(ws, e) for e in entries]
    return Outcome(stage=a["stage"], data={"removed": removed, "dry_run": a["dry_run"]})
