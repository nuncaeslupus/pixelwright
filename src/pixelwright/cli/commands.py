"""Command handlers. Each takes the workspace root and parsed arguments, returns an Outcome."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from pixelwright.cli.registry import EXIT_CHECK, Outcome, Param, PwError, command
from pixelwright.core import checks as C
from pixelwright.core.clean import clean
from pixelwright.core.image import Image, IndexedImage, RGBImage
from pixelwright.core.palette import Color, Palette, Ramps, analyze_ramp, propose_ramps
from pixelwright.core.quantize import discover_palette, quantize_fixed
from pixelwright.core.render import grayscale, overlay, upscale, value_map
from pixelwright.core.snap import snap
from pixelwright.io.aseprite import flatten_frames, read_aseprite
from pixelwright.io.palette_io import read_palette, read_ramps, write_palette, write_ramps
from pixelwright.io.png import encode_png, read_png, write_png
from pixelwright.workspace import Asset, Workspace, WorkspaceConfig, critique
from pixelwright.workspace.asset import KINDS
from pixelwright.workspace.files import sha256_bytes, write_bytes_atomic
from pixelwright.workspace.schema import SchemaError
from pixelwright.workspace.style import bump_style, load_ramps, style_path

Mask = npt.NDArray[np.bool_]
IMAGE = "image.png"
ASEPRITE = "image.aseprite"
VIEWS = ("upscale", "gray", "values", "silhouette", "overlay", "gif", "apng")

ASSET = Param("asset", help="asset id", required=True, positional=True)
VERSION = Param("version", help="version (default: latest)")
MASK = Param("mask", help="issue (mask) id: change only pixels inside its region")
RESOLVE = Param("resolve", "bool", help="mark the --mask issue fixed by the new version")


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
    ws: Workspace,
    asset: Asset,
    step: str,
    image: Image,
    parent: str | None,
    extra: Mapping[str, bytes] | None = None,
    **params: Any,
) -> Outcome:
    files = {IMAGE: encode_png(image), **(extra or {})}
    version = asset.new_version(step, files, params=params, parent=parent)
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


def _keep_outside(new: Image, old: Image, region: Mask) -> Image:
    """`new` inside `region`, `old` everywhere else, pixel for pixel."""
    if (
        isinstance(new, IndexedImage)
        and isinstance(old, IndexedImage)
        and new.palette == old.palette
    ):
        indices = np.where(region, new.indices, old.indices).astype(np.uint16)
        opaque = np.where(region, new.opaque(), old.opaque())
        return IndexedImage(indices, new.palette, None if opaque.all() else opaque)
    old_rgba = old.rgba if isinstance(old, RGBImage) else old.to_rgba()
    new_rgba = new.rgba if isinstance(new, RGBImage) else new.to_rgba()
    return RGBImage(np.where(region[..., None], new_rgba, old_rgba).astype(np.uint8))


def _resolved(asset: Asset, a: dict[str, Any], outcome: Outcome) -> Outcome:
    """With `--resolve`, mark the `--mask` issue fixed by the version just made."""
    if a["resolve"]:
        assert outcome.version is not None
        asset.resolve_issue(a["mask"], outcome.version, author="claude")
        outcome.data["resolved"] = a["mask"]
    return outcome


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
    Param("aseprite", help="the .aseprite the image was saved from; kept as image.aseprite"),
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
        extra: dict[str, bytes] = {}
        if a["aseprite"]:
            ase = Path(a["aseprite"])
            if not ase.is_file():
                raise PwError("not_found", f"no such file: {ase}")
            read_aseprite(ase)  # refuse a file the codec cannot read
            extra[ASEPRITE] = ase.read_bytes()
        outcome = _publish(ws, asset, "attach", image, parent, extra, file=src.name)
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
    MASK,
    RESOLVE,
)
def cmd_quantize(root: Path, a: dict[str, Any]) -> Outcome:
    if a["resolve"] and not a["mask"]:
        raise PwError("invalid", "--resolve needs --mask")
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
    region = _mask(asset, a["mask"], (rgb.height, rgb.width))
    result = indexed if region is None else _keep_outside(indexed, image, region)
    params = {k: a[k] for k in ("palette", "discover", "dither_mask", "mask") if a[k]}
    outcome = _publish(ws, asset, "quantize", result, parent, **params)
    outcome.data = {**asdict(report), "colors": len(palette)}
    return _resolved(asset, a, outcome)


@command(
    "clean",
    "remove orphan pixels (and isolated pairs), optionally inside a mask",
    ASSET,
    VERSION,
    MASK,
    Param("pairs", "bool", help="also remove isolated two-pixel clusters"),
    RESOLVE,
)
def cmd_clean(root: Path, a: dict[str, Any]) -> Outcome:
    if a["resolve"] and not a["mask"]:
        raise PwError("invalid", "--resolve needs --mask")
    ws = Workspace.open(root)
    asset = ws.asset(a["asset"])
    parent = _version(asset, a["version"])
    image = _indexed(_image(asset, parent), "clean")
    region = _mask(asset, a["mask"], image.indices.shape)
    cleaned, report = clean(image, region, pairs=a["pairs"])
    params = {k: a[k] for k in ("mask", "pairs") if a[k]}
    outcome = _publish(ws, asset, "clean", cleaned, parent, **params)
    outcome.data = asdict(report)
    return _resolved(asset, a, outcome)


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
    ase = asset.versions_dir / version / ASEPRITE
    data = {"view": view, "source": source, "open": _rel(ws, ase) if ase.is_file() else source}
    return Outcome(asset.id, version, asset.stage(version), [_rel(ws, out)], data)


def _render_animation(ws: Workspace, asset: Asset, version: str, view: str, scale: int) -> Outcome:
    """GIF or APNG of the version's frames (from image.aseprite, else the single PNG)."""
    from PIL import Image as PILImage

    ase = asset.versions_dir / version / ASEPRITE
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
        choices=("import", "discover", "show", "edit"),
    ),
    Param("file", help="palette file (.gpl or .hex) for import"),
    Param("asset", help="asset id for discover"),
    Param("version", help="version for discover (default: latest)"),
    Param("colors", "int", help="number of colors for discover", default=16),
    Param("name", help="file name under style/palettes/ (default: from the source)"),
    Param("set", "list", help="edit: replace colors, as INDEX=RRGGBB"),
    Param("add", "list", help="edit: append colors, as RRGGBB"),
    Param("remove", "list", help="edit: drop colors by index"),
    Param("order", help="edit: new order as comma-separated indices, e.g. 2,0,1"),
)
def cmd_palette(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    folder = ws.path("style") / "palettes"
    if a["action"] == "edit":
        return _palette_edit(ws, folder, a)
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


def _palette_edit(ws: Workspace, folder: Path, a: dict[str, Any]) -> Outcome:
    if not a["name"]:
        raise PwError("invalid", "palette edit needs --name")
    path = folder / str(a["name"]).removeprefix("palettes/")
    if not path.is_file():
        raise PwError("not_found", f"no such palette: {a['name']}")
    colors = list(read_palette(path).colors)
    try:
        for item in a["set"]:
            index, _, value = item.partition("=")
            colors[int(index)] = Color.from_hex(value, colors[int(index)].name)
        for index in sorted({int(i) for i in a["remove"]}, reverse=True):
            del colors[index]
        colors += [Color.from_hex(v) for v in a["add"]]
        if a["order"]:
            order = [int(i) for i in a["order"].split(",")]
            if sorted(order) != list(range(len(colors))):
                raise ValueError(f"--order must list each of the {len(colors)} indices once")
            colors = [colors[i] for i in order]
    except (ValueError, IndexError) as exc:
        raise PwError("invalid", f"palette edit: {exc}") from exc
    old = read_palette(path)
    palette = Palette(colors, old.name, old.columns)
    write_palette(path, palette)
    rel = _register_palette(ws, path, note=f"palette edit: {path.name}")
    data: dict[str, Any] = {
        "palette": rel,
        "colors": len(palette),
        "ramps": _recheck_ramps(ws, path, palette),
    }
    warnings = [f"ramp {r['ramp']}: {r['error']}" for r in data["ramps"] if "error" in r]
    return Outcome(outputs=[_rel(ws, path)], data=data, warnings=warnings)


def _recheck_ramps(ws: Workspace, path: Path, palette: Palette) -> list[dict[str, Any]]:
    """Re-analyze the style's ramps when they index into the edited palette."""
    guide = ws.style()
    if not guide.ramps:
        return []
    ramps_file = ws.path("style") / guide.ramps
    ramps = read_ramps(ramps_file)
    target = (ramps_file.parent / ramps.palette).resolve() if ramps.palette else None
    if target != path.resolve():
        return []
    rows: list[dict[str, Any]] = []
    for name, ramp in ramps.ramps.items():
        if any(not 0 <= i < len(palette) for i in ramp.indices):
            rows.append({"ramp": name, "error": "indices outside the palette"})
            continue
        report = analyze_ramp(palette, ramp)
        rows.append(
            {
                "ramp": name,
                "monotonic_lightness": report.monotonic_lightness,
                "hue_shift_deg": round(report.hue_shift_deg, 1),
            }
        )
    return rows


def _style_propose(ws: Workspace, a: dict[str, Any]) -> Outcome:
    style_dir = ws.path("style")
    files = [Path(f) for f in a["file"]] or [
        *(style_dir / r for r in ws.style().references),
        *sorted((style_dir / "references").glob("*.png")),
    ]
    files = [f for f in dict.fromkeys(files) if f.suffix.lower() == ".png"]
    if not files:
        raise PwError("invalid", "style propose needs reference PNGs (--file or style/references/)")
    pixels = []
    for f in files:
        if not f.is_file():
            raise PwError("not_found", f"no such file: {f}")
        rgba = read_png(f).to_rgba().reshape(-1, 4)
        pixels.append(rgba[rgba[:, 3] > 0])
    stacked = np.concatenate(pixels)[None, :, :]
    palette = discover_palette(RGBImage(np.ascontiguousarray(stacked)), a["colors"])
    pal_path = style_dir / "palettes" / "proposed.gpl"
    ramps_path = style_dir / "palettes" / "proposed-ramps.yaml"
    write_palette(pal_path, palette)
    ramps = propose_ramps(palette)
    ramps.palette = pal_path.name
    write_ramps(ramps_path, ramps)
    data = {
        "palette": _rel_style(ws, pal_path),
        "ramps": {n: [palette[i].hex for i in r.indices] for n, r in ramps.ramps.items()},
        "references": [str(f) for f in files],
    }
    return Outcome(outputs=[_rel(ws, pal_path), _rel(ws, ramps_path)], data=data)


def _style_test(ws: Workspace, root: Path, a: dict[str, Any]) -> Outcome:
    ids = a["assets"] or ws.style().test_assets
    if not ids:
        raise PwError("invalid", "no test assets: pass --assets or set test_assets in the style")
    rows, warnings = [], []
    for asset_id in ids:
        args: dict[str, Any] = {
            "asset": asset_id,
            "version": None,
            "checks": [],
            "mask": None,
            "layers": [],
        }
        out = cmd_check(root, {**args, "file": None, "scale": 1})
        failed = [r["check"] for r in out.data["results"] if r["status"] == "fail"]
        rows.append({"asset": asset_id, "version": out.version, "failed": failed, **out.data})
        warnings += [f"{asset_id}: {w}" for w in out.warnings]
    data = {
        "style_version": ws.style().version,
        "assets": rows,
        "passed": not any(r["failed"] for r in rows),
    }
    return Outcome(outputs=[_rel(ws, style_path(ws.path("style")))], data=data, warnings=warnings)


@command(
    "style",
    "show, bump, propose (palette and ramps from references) or test the style guide",
    Param(
        "action",
        help="what to do",
        required=True,
        positional=True,
        choices=("show", "bump", "propose", "test"),
    ),
    Param("changes", help='JSON object of fields to change, e.g. {"notes": "..."}'),
    Param("note", help="why", default=""),
    Param("file", "list", help="propose: reference PNGs (default: style/references/)"),
    Param("colors", "int", help="propose: palette size", default=16),
    Param("assets", "list", help="test: asset ids (default: the style's test_assets)"),
)
def cmd_style(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    if a["action"] == "propose":
        return _style_propose(ws, a)
    if a["action"] == "test":
        return _style_test(ws, root, a)
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


# -- issues, history, status, inbox -------------------------------------------------
@command(
    "issue",
    "add, list or resolve issues (a region, a rule, a note) on an asset",
    ASSET,
    Param(
        "action",
        help="what to do",
        required=True,
        positional=True,
        choices=("add", "list", "resolve"),
    ),
    Param("id", help="issue id (add: default derived from the rule; resolve: required)"),
    Param("file", help="mask PNG (white = inside) for add"),
    Param("box", help="x,y,w,h in native pixels for add"),
    Param("version", help="version the issue is about (add) or that fixes it (resolve)"),
    Param("rule", help="rule id, e.g. R-PIX-3", default=""),
    Param("note", help="free text", default=""),
    Param("author", help="who raises it", default="claude", choices=("human", "claude", "check")),
    Param("status", help="list filter", default="all", choices=("open", "fixed", "all")),
)
def cmd_issue(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    asset = ws.asset(a["asset"])
    if a["action"] == "list":
        found = [i for i in asset.issues() if a["status"] in ("all", i["status"])]
        if a["version"]:
            found = [i for i in found if i["version"] in (a["version"], None)]
        return Outcome(asset.id, data={"issues": found})
    if a["action"] == "resolve":
        if not a["id"]:
            raise PwError("invalid", "issue resolve needs --id")
        version = _version(asset, a["version"])
        try:
            entry = asset.resolve_issue(a["id"], version, author=a["author"])
        except KeyError as err:
            raise PwError("issue_not_found", str(err)) from err
        return Outcome(asset.id, version, asset.stage(version), data={"issue": entry})
    version = _version(asset, a["version"])
    issue_id = a["id"] or _issue_id(asset, a["rule"])
    box = _box(a["box"]) if a["box"] else None
    png = Path(a["file"]).read_bytes() if a["file"] else None
    try:
        entry = asset.add_issue(
            issue_id,
            png=png,
            box=box,
            version=version,
            rule=a["rule"],
            note=a["note"],
            author=a["author"],
        )
    except (ValueError, FileExistsError) as err:
        raise PwError("invalid", str(err)) from err
    return Outcome(asset.id, version, asset.stage(version), data={"issue": entry})


def _issue_id(asset: Asset, rule: str) -> str:
    stem = "".join(ch if ch.isalnum() else "-" for ch in (rule or "issue").lower()).strip("-")
    stem = "-".join(part for part in stem.split("-") if part) or "issue"
    taken = {i["id"] for i in asset.issues()}
    n = 1
    while f"{stem}-{n}" in taken:
        n += 1
    return f"{stem}-{n}"


def _box(text: str) -> tuple[int, int, int, int]:
    parts = text.split(",")
    if len(parts) != 4 or not all(p.strip().isdigit() for p in parts):
        raise PwError("invalid", f"box must be x,y,w,h, got {text!r}")
    x, y, w, h = (int(p) for p in parts)
    return x, y, w, h


@command(
    "history",
    "the asset's log, newest first",
    ASSET,
    Param("since", help="only entries at or after this ISO time"),
    Param("limit", "int", help="at most this many entries", default=50),
)
def cmd_history(root: Path, a: dict[str, Any]) -> Outcome:
    asset = Workspace.open(root).asset(a["asset"])
    entries = [h for h in reversed(asset.history()) if not a["since"] or h["time"] >= a["since"]]
    return Outcome(asset.id, data={"history": entries[: a["limit"]]})


def _asset_status(asset: Asset) -> dict[str, Any]:
    versions = asset.versions()
    newest = versions[-1] if versions else None
    decided = {d["version"] for d in asset.decisions()}
    report = asset.versions_dir / newest / "report.json" if newest else None
    flagged = None
    if report is not None and report.exists():
        flagged = sum(r["status"] != "pass" for r in C.read_report(report))
    return {
        "asset": asset.id,
        "kind": asset.spec()["kind"],
        "versions": [{"version": v, "stage": asset.stage(v)} for v in versions],
        "newest": newest,
        "waiting_for_decision": newest is not None and newest not in decided,
        "flagged_checks": flagged,
        "open_issues": sum(i["status"] == "open" for i in asset.issues()),
    }


@command(
    "status",
    "versions, stages, open issues and what an asset is waiting on",
    Param("asset", help="asset id (default: every asset)", positional=True),
)
def cmd_status(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    ids = [a["asset"]] if a["asset"] else ws.assets()
    return Outcome(a["asset"], data={"assets": [_asset_status(ws.asset(i)) for i in ids]})


@command(
    "inbox",
    "what others did since you last acted (default: since Claude's last entry)",
    Param("since", help="ISO time (default: after the reader's own last entry, per asset)"),
    Param("reader", help="whose inbox", default="claude", choices=("claude", "human")),
)
def cmd_inbox(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    items: list[dict[str, Any]] = []
    for asset_id in ws.assets():
        log = ws.asset(asset_id).history()
        since = a["since"]
        if since is None:
            own = [h["time"] for h in log if h.get("author") == a["reader"]]
            since = own[-1] if own else ""
        items += [
            {"asset": asset_id, **h}
            for h in log
            if h["time"] > since and h.get("author") != a["reader"]
        ]
    items.sort(key=lambda h: h["time"])
    return Outcome(data={"items": items, "count": len(items)})


# -- critique -------------------------------------------------------------------------
@command(
    "critique",
    "write or show Claude's critique of a version (critique.md, complaints linked to issues)",
    ASSET,
    Param("action", help="what to do", required=True, positional=True, choices=("write", "show")),
    VERSION,
    Param("file", help="critique.md to store (write)"),
)
def cmd_critique(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    asset = ws.asset(a["asset"])
    version = _version(asset, a["version"])
    dest = asset.versions_dir / version / "critique.md"
    if a["action"] == "write":
        if not a["file"]:
            raise PwError("invalid", "critique write needs --file")
        text = Path(a["file"]).read_text(encoding="utf-8")
        parsed = _parse_critique(text)
        if parsed.version != version:
            raise PwError("invalid", f"critique is about {parsed.version}, not {version}")
        known = {i["id"] for i in asset.issues()}
        unknown = [k.issue for k in parsed.complaints if k.issue and k.issue not in known]
        if unknown:
            raise PwError("issue_not_found", f"unknown issue ids: {', '.join(unknown)}")
        dest.write_text(text, encoding="utf-8")
        asset.note(f"critique: {parsed.verdict}", author="claude", version=version)
        return Outcome(asset.id, version, asset.stage(version), [_rel(ws, dest)], parsed.to_dict())
    if not dest.exists():
        raise PwError("not_found", f"{asset.id} {version} has no critique.md")
    parsed = _parse_critique(dest.read_text(encoding="utf-8"))
    return Outcome(asset.id, version, asset.stage(version), [_rel(ws, dest)], parsed.to_dict())


def _parse_critique(text: str) -> critique.Critique:
    try:
        return critique.parse(text)
    except (SchemaError, ValueError) as err:
        raise PwError("invalid", f"critique.md: {err}") from err
