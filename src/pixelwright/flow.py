"""The steps of the flow on the v2 project model: normalise, check, and what comes next.

Scripts always run first (normalise, check); the AI and the person act on the issues.
`next_step` names the single next step of an asset and who owes it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from PIL import Image as PILImage

from pixelwright.asset import Asset, AssetError
from pixelwright.core.abstract import kuwahara, remove_small_clusters
from pixelwright.core.checks import CheckResult, check_banding, check_line_runs, check_orphans
from pixelwright.core.clean import clean
from pixelwright.core.color import srgb8_to_oklab
from pixelwright.core.image import IndexedImage, RGBImage
from pixelwright.core.importance import ColorGroup, analyze_colors, importance_map
from pixelwright.core.lines import regularise_lines
from pixelwright.core.palette import Color, Palette
from pixelwright.core.quantize import ACCENT_BOOST, MAX_ACCENTS, discover_palette, quantize_fixed
from pixelwright.core.ramps import hue_families
from pixelwright.core.snap import finer_canvas_grid, snap
from pixelwright.core.sprite import background, frame, key_background, outline_reduce
from pixelwright.io.palette_io import read_palette
from pixelwright.io.png import read_png
from pixelwright.issues import Issue, IssueLog
from pixelwright.project import Project
from pixelwright.rules import raise_check_issues

DISCOVERED_COLORS = 16  # plus up to MAX_ACCENTS kept for small important colours
PAINTING_COLORS = 24  # a reduced painting has no palette of its own to recover
SPECK = 4  # in a reduced painting, same-colour groups this small are texture, not shape
RICH = 24  # with more palette colours than this, a grid-snapped input's detail is meant
FAITHFUL_DE = 0.02  # ... so clean undoes a change that moves a pixel this much further
PROTECT = 0.8  # pixels at least this important are never cleaned away
GLOW = 0.5  # ... nor their neighbours this important: the arms of a twinkle, not JPEG noise
OVERSIZE = 1.25  # a snapped image this much larger than the canvas has no real pixel grid
UNDERSIZE = 0.5  # ... or this much smaller, while the image itself is larger than the canvas
NEAR = 0.15  # a grid this close to the canvas size is the canvas grid
OWN_COLORS = 256  # pixel art on its grid with at most this many colours keeps them exactly
# with more palette colours than RICH, dithering and texture are the style: the checks
# allow a density of flagged pixels that real 256-colour VGA scenes reach (65-215 per
# mille of orphans, 4-12 per mille of line-run pixels) and only very long bands
RICH_ORPHANS = 0.25
RICH_LINE_RUNS = 0.02
RICH_BAND = 0.6  # of the image's shorter side


@dataclass
class NormalizeResult:
    version: str
    scale: int  # detected pixel size in source pixels (1 when reduced to the canvas)
    size: tuple[int, int]
    palette: str
    warnings: list[str]
    reduced: bool = False  # no pixel grid near the canvas: the image was scaled down to it


def asset_palette(asset: Asset) -> Palette | None:
    """The asset's first palette from the library, or None when the file is missing."""
    name = asset.settings().palette
    path = asset.project.palettes_dir / f"{name}.gpl"
    return read_palette(path) if path.is_file() else None


def _rgb(path: Path) -> RGBImage:
    image = read_png(path)
    return image if isinstance(image, RGBImage) else image.to_rgb_image()


def _pil(image: IndexedImage | RGBImage) -> PILImage.Image:
    return PILImage.fromarray(np.ascontiguousarray(image.to_rgba()), mode="RGBA")


def reduce_to_canvas(
    image: RGBImage, canvas: tuple[int, int], *, simplify: bool = False
) -> RGBImage:
    """Scale an image without a usable pixel grid (a painting, a photo) down to fit the
    canvas, keeping its aspect ratio; each new pixel is the area average of the old ones.
    `simplify` first flattens brush texture while keeping edges (`core.abstract.kuwahara`)."""
    factor = min(canvas[0] / image.width, canvas[1] / image.height)
    if simplify and factor < 0.5:
        rgba = image.rgba.astype(np.float64)
        flat = kuwahara(rgba[..., :3], max(1, round(0.5 / factor)))
        rgba[..., :3] = flat
        image = RGBImage(np.clip(np.rint(rgba), 0, 255).astype(np.uint8))
    size = (max(1, round(image.width * factor)), max(1, round(image.height * factor)))
    small = PILImage.fromarray(np.ascontiguousarray(image.rgba), "RGBA").resize(
        size, PILImage.Resampling.BOX
    )
    return RGBImage(np.asarray(small, dtype=np.uint8).copy())


@dataclass
class Prepared:
    """An input brought to pixel scale, before any palette: what normalize quantizes."""

    image: RGBImage
    scale: int
    reduced: bool
    warnings: list[str]


def _source(asset: Asset, source: Path | None) -> Path:
    if source is not None:
        return source
    inputs = asset.inputs()
    if not inputs:
        raise AssetError(f"{asset.rel}: no input to normalise; add an image first")
    return inputs[-1]


def prepare(asset: Asset, source: Path | None = None) -> Prepared:
    """Detect the pixel grid of an input, or reduce it to the canvas when it has none."""
    source_rgb = _rgb(_source(asset, source))
    canvas = asset.settings().canvas
    cw, ch = canvas["width"], canvas["height"]
    if (source_rgb.width, source_rgb.height) == (cw, ch):
        # drawn at the canvas size, as pixel-native providers do: each pixel is a cell
        # already, and a grid found on it would be a false, coarser one (34x18)
        return Prepared(source_rgb, 1, False, [])
    larger = source_rgb.width > cw and source_rgb.height > ch
    bg = background(source_rgb) if larger else None
    snapped = snap(source_rgb)
    if bg:  # a sprite on a flat background: key it on its own pixel grid, frame it
        sprite = snapped.image if snapped.scale > 1 else source_rgb
        keyed = key_background(sprite, bg)
        if keyed is not None:
            return _sprite(frame(keyed, (cw, ch)), (cw, ch), bg)
    native = snapped.image
    off = abs(native.width / cw - 1) > NEAR or abs(native.height / ch - 1) > NEAR
    if off and source_rgb.width > cw * OVERSIZE and source_rgb.height > ch * OVERSIZE:
        # the grid found may be a multiple of the real one (8 px for 4.2 px cells): pixel
        # art drawn at the canvas size would come out at half its detail
        fitted = finer_canvas_grid(source_rgb, (cw, ch), snapped.period[0] or snapped.scale)
        if fitted is not None:
            snapped, native = fitted, fitted.image
    too_big = native.width > cw * OVERSIZE and native.height > ch * OVERSIZE
    too_small = (  # a coarse false grid on a big painting: 80x44 for a 320x180 scene
        native.width < cw * UNDERSIZE
        and native.height < ch * UNDERSIZE
        and source_rgb.width > cw
        and source_rgb.height > ch
    )
    if too_big or too_small:
        small = reduce_to_canvas(source_rgb, (cw, ch), simplify=True)
        return Prepared(small, 1, True, [
            f"no pixel grid near the canvas (snapped {native.width}x{native.height}); "
            f"reduced {source_rgb.width}x{source_rgb.height} to {small.width}x{small.height}"
        ])  # fmt: skip
    warnings = []
    if (native.width, native.height) != (cw, ch):
        warnings.append(
            f"snapped size {native.width}x{native.height} (scale {snapped.scale}) "
            f"differs from the canvas {cw}x{ch}"
        )
    return Prepared(native, snapped.scale, False, warnings)


def _sprite(framed: RGBImage, canvas: tuple[int, int], bg: tuple[int, int, int]) -> Prepared:
    """A keyed, framed sprite on the canvas: as drawn when it fits, else reduced."""
    hexa = "#{:02x}{:02x}{:02x}".format(*bg)
    cw, ch = canvas
    if framed.width <= cw and framed.height <= ch:  # pad, centred, feet at the bottom
        out = np.zeros((ch, cw, 4), np.uint8)
        x, y = (cw - framed.width) // 2, ch - framed.height
        out[y:, x : x + framed.width] = framed.rgba
        return Prepared(RGBImage(out), 1, False, [f"background {hexa} made transparent"])
    return Prepared(outline_reduce(framed, canvas), 1, False, [
        f"background {hexa} made transparent; the figure is drawn {framed.width}x"
        f"{framed.height} px, reduced to the {cw}x{ch} canvas (detail is lost: a canvas "
        f"near {framed.width}x{framed.height} keeps it)"
    ])  # fmt: skip


def _grow(mask: npt.NDArray[np.bool_]) -> npt.NDArray[np.bool_]:
    """The mask plus its 4-neighbours."""
    out = mask.copy()
    out[1:] |= mask[:-1]
    out[:-1] |= mask[1:]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    return out


def _glow(
    indexed: IndexedImage, native: RGBImage, imp: npt.NDArray[np.float64], palette: Palette
) -> tuple[IndexedImage, npt.NDArray[np.bool_]]:
    """Pixels never to clean: the important ones and the glow right around them. The glow
    of a lone bright pixel (a twinkling star) takes one colour, the palette colour
    nearest its mean, instead of one per pixel."""
    core = imp >= PROTECT
    protect = core | (_grow(core) & (imp >= GLOW))
    indices = indexed.indices.copy()
    h, w = core.shape
    for y, x in zip(*np.nonzero(core), strict=True):
        diagonals = [
            (y + dy, x + dx)
            for dy in (-1, 1)
            for dx in (-1, 1)
            if 0 <= y + dy < h and 0 <= x + dx < w
        ]
        if (
            any(protect[p] for p in diagonals)
            or imp[y, x] < imp[max(0, y - 1) : y + 2, max(0, x - 1) : x + 2].max()
        ):
            continue  # part of a shape (a lamp), or an arm itself: not the star's centre
        arms = [
            (y + dy, x + dx)
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1))
            if 0 <= y + dy < h and 0 <= x + dx < w and protect[y + dy, x + dx]
        ]
        if len(arms) < 2:
            continue
        mean = np.mean([native.rgba[p] for p in arms], axis=0).round().astype(np.uint8)
        one, _ = quantize_fixed(RGBImage(mean.reshape(1, 1, 4)), palette)
        for p in arms:
            indices[p] = one.indices[0, 0]
    return IndexedImage(indices, indexed.palette, indexed.alpha), protect


def _faithful(cleaned: IndexedImage, indexed: IndexedImage, native: RGBImage) -> IndexedImage:
    """`cleaned` with each change undone that takes a pixel further from the input than
    quantising did (by FAITHFUL_DE): in rich pixel art a lone pixel is a highlight or a
    crack, not noise; only near-equal flecks left by quantising are cleaned away."""
    lab = srgb8_to_oklab(native.rgba[..., :3])

    def err(image: IndexedImage) -> npt.NDArray[np.float64]:
        return np.asarray(np.linalg.norm(srgb8_to_oklab(image.to_rgba()[..., :3]) - lab, axis=-1))

    both = np.ones(lab.shape[:2], bool)
    for image in (cleaned, indexed):
        if image.alpha is not None:
            both &= image.alpha
    undo = both & (err(cleaned) > err(indexed) + FAITHFUL_DE)
    indices = np.where(undo, indexed.indices, cleaned.indices).astype(np.uint16)
    return IndexedImage(indices, cleaned.palette, cleaned.alpha)


def _own_colors(image: RGBImage) -> list[Color]:
    """The image's distinct opaque colours, dark to light."""
    rgba = image.rgba.reshape(-1, 4)
    rgb = np.unique(rgba[rgba[:, 3] >= 128][:, :3], axis=0)
    return [Color(int(r), int(g), int(b)) for r, g, b in rgb[np.argsort(rgb.sum(axis=1))]]


def normalize(asset: Asset, source: Path | None = None) -> NormalizeResult:
    """Input → next version: pixel grid (or reduce to the canvas), palette, stray pixels."""
    prep = prepare(asset, source)
    native, warnings = prep.image, list(prep.warnings)
    imp = importance_map(native)
    settings = asset.settings()
    palette = None if settings.colors else asset_palette(asset)
    palette_name = settings.palette
    if settings.colors:  # `colors = N`: the input's own N colours, accents included
        n = settings.colors
        palette = discover_palette(native, n - MAX_ACCENTS if n > 2 * MAX_ACCENTS else n,
                                   importance=imp)  # fmt: skip
        palette_name = f"discovered ({n})"
    elif palette is None and not prep.reduced and len(own := _own_colors(native)) <= OWN_COLORS:
        # already pixel art on its grid: its colours are meant, keep every pixel as drawn
        warnings.append(f"palette {palette_name!r} not in style/palettes; own colours kept")
        version = asset.add_version(_pil(quantize_fixed(native, Palette(own))[0]))
        if asset.meta().state == "processing":
            asset.set_state("review")
        size = (native.width, native.height)
        return NormalizeResult(version, prep.scale, size, f"own ({len(own)})", warnings)
    elif palette is None:
        warnings.append(f"palette {palette_name!r} not in style/palettes; colours discovered")
        colors = PAINTING_COLORS if prep.reduced else DISCOVERED_COLORS
        palette = discover_palette(native, colors, importance=imp)
        palette_name = "discovered"
    indexed, _ = quantize_fixed(native, palette)
    # a lone pixel that stands out strongly (a star, a glint) is meant, not noise
    indexed, protect = _glow(indexed, native, imp, palette)
    cleaned, _ = clean(indexed, ~protect)
    if not prep.reduced and len(palette) > RICH:
        cleaned = _faithful(cleaned, indexed, native)
    if prep.reduced:  # a painting: fold leftover texture specks into their shapes
        cleaned, _ = remove_small_clusters(cleaned, SPECK, protect=protect)
    version = asset.add_version(_pil(cleaned))
    if asset.meta().state == "processing":
        asset.set_state("review")
    size = (native.width, native.height)
    return NormalizeResult(version, prep.scale, size, palette_name, warnings, prep.reduced)


ANALYSIS = "analysis"


@dataclass
class ColorAnalysis:
    groups: list[ColorGroup]
    heatmap: Path  # importance per pixel, white = matters most
    prepared: Prepared


def analyze(asset: Asset, source: Path | None = None) -> ColorAnalysis:
    """Analyse an input's colours as normalize will see them: groups, accents and an
    importance heatmap saved as `analysis/importance.png` in the asset folder."""
    prep = prepare(asset, source)
    imp = importance_map(prep.image)
    folder = asset.path / ANALYSIS
    folder.mkdir(exist_ok=True)
    heatmap = folder / "importance.png"
    PILImage.fromarray((imp * 255).round().astype(np.uint8), "L").save(heatmap)
    return ColorAnalysis(analyze_colors(prep.image, imp), heatmap, prep)


def run_checks(asset: Asset, version: str | None = None) -> tuple[list[CheckResult], list[Issue]]:
    """Run the pixel checks on a version and raise `script` issues for what they flag."""
    version = version or asset.latest()
    if version is None:
        raise AssetError(f"{asset.rel}: no version to check")
    native = _rgb(asset.version_path(version))
    palette = asset_palette(asset)
    if palette is None:
        own = _own_colors(native)
        palette = Palette(own) if len(own) <= OWN_COLORS else discover_palette(native, OWN_COLORS)
    indexed, _ = quantize_fixed(native, palette)
    if len(palette) > RICH:
        area, side = native.width * native.height, min(native.width, native.height)
        results = [
            check_orphans(indexed, int(area * RICH_ORPHANS)),
            check_line_runs(indexed, int(area * RICH_LINE_RUNS)),
            check_banding(indexed, max(12, int(side * RICH_BAND))),
        ]
    else:
        results = [check_orphans(indexed), check_line_runs(indexed), check_banding(indexed)]
    log = IssueLog(asset)
    issues = raise_check_issues(log, version, results)
    for issue in issues:  # the scripts can propose a fix for jaggy lines themselves
        if issue.rule == "R-PIX-4":
            lines, count = regularise_lines(indexed)
            if count:
                log.propose_fix(
                    issue.id, _pil(lines), by="script", base=version,
                    op={"script": "regularise_lines", "lines": count},
                )  # fmt: skip
    return results, issues


@dataclass(frozen=True)
class NextStep:
    step: str
    actor: str  # you | ai | scripts | none
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"step": self.step, "actor": self.actor, "text": self.text}


def next_step(asset: Asset) -> NextStep:
    meta = asset.meta()
    latest = asset.latest()
    if latest is None:
        if asset.inputs():
            return NextStep("normalize", "scripts", "Clean up the input into v001")
        return NextStep("add", "you", "Add an image to start")
    log = IssueLog(asset)
    if log.pending_for_ai():
        return NextStep("ai", "ai", "Waiting on the AI")
    if meta.state == "finished" and meta.final == latest:
        return NextStep("none", "none", f"Finished · {latest}")
    st = log.state()
    open_issues = [i for i in st.issues.values() if i.state == "open"]
    with_fix = [i for i in open_issues if any(st.fixes[f].state == "proposed" for f in i.fixes)]
    if with_fix:
        n = len(with_fix)
        return NextStep("decide", "you", f"{n} fix{'es' if n > 1 else ''} to look at")
    if open_issues:
        return NextStep("fix", "you", f"{len(open_issues)} open issue(s) without a fix")
    return NextStep("finish", "you", f"Finish with {latest}?")


def status(assets: list[Asset]) -> list[dict[str, Any]]:
    rows = []
    for asset in assets:
        meta = asset.meta()
        rows.append(
            {
                "asset": asset.rel,
                "state": meta.state,
                "latest": asset.latest(),
                "final": meta.final,
                "next": next_step(asset).to_dict(),
            }
        )
    return rows


IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")


def asset_name(stem: str) -> str:
    """A kebab-case asset name from a file name: 'Tavern 1.png' → 'tavern-1'."""
    out = "".join(c if c.isalnum() else "-" for c in stem.lower())
    return "-".join(p for p in out.split("-") if p) or "image"


def ingest(project: Project, image: Path, category: str, *, move: bool = False) -> Asset:
    """Make an asset from an image under `category`, then let the scripts run
    (normalise, check). Script failures leave the asset in Processing, never lose the input."""
    from pixelwright.asset import Asset as AssetCls

    base = asset_name(image.stem)
    name, n = base, 2
    while (project.assets_dir / category / name).exists():
        name, n = f"{base}-{n}", n + 1
    asset = AssetCls.create(project, f"{category}/{name}")
    asset.add_input(image)
    if move:
        image.unlink()
    try:
        normalize(asset)
        run_checks(asset)
    except (ValueError, OSError):
        pass  # stays in Processing; the app shows it and the person can retry
    return asset


def scan(project: Project) -> list[Asset]:
    """Pick up images saved straight into a category folder (not inside an asset)."""
    found: list[Asset] = []
    if not project.assets_dir.is_dir():
        return found
    for folder in sorted(p for p in project.assets_dir.rglob("*") if p.is_dir()):
        if (folder / "asset.toml").is_file() or any(
            (parent / "asset.toml").is_file() for parent in folder.parents
        ):
            continue
        category = folder.relative_to(project.assets_dir).as_posix()
        for image in sorted(folder.iterdir()):
            if image.is_file() and image.suffix.lower() in IMAGE_SUFFIXES:
                found.append(ingest(project, image, category, move=True))
    return found


def _side_by_side(
    images: list[RGBImage],
) -> tuple[RGBImage, npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Images in one row (transparent padding), their importance, and a per-pixel scale
    that makes each image count the same, small or large."""
    if not images:
        raise ValueError("no images to take colours from")
    h = max(im.height for im in images)
    w = sum(im.width for im in images)
    rgba = np.zeros((h, w, 4), np.uint8)
    imp, scale = np.zeros((h, w)), np.zeros((h, w))
    x = 0
    for im in images:
        rgba[: im.height, x : x + im.width] = im.rgba
        imp[: im.height, x : x + im.width] = importance_map(im)
        opaque = max(1, int((im.rgba[..., 3] >= 128).sum()))
        scale[: im.height, x : x + im.width] = 1e4 / opaque
        x += im.width
    return RGBImage(rgba), imp, scale


def palette_from(images: list[RGBImage], n: int) -> Palette:
    """One palette of about `n` colours (plus accents) shared by several images at pixel
    scale: a scene set's or a cast's colours; each image counts the same."""
    joined, imp, scale = _side_by_side(images)
    return discover_palette(joined, n, importance=imp, scale=scale)


def ramp_keys_from(images: list[RGBImage], n: int) -> dict[str, str]:
    """Key colours for `n` ramps: the images' hue families (core.ramps.hue_families)."""
    joined, imp, scale = _side_by_side(images)
    opaque = joined.rgba[..., 3] >= 128
    lab = srgb8_to_oklab(joined.rgba[..., :3][opaque])
    weight = scale * (1 + ACCENT_BOOST * imp**2)  # small lights (fire, candles) count more
    return hue_families(lab, weight[opaque], n)


SWATCH = 24  # px per colour in a palette swatch
SWATCH_ROW = 16


def write_swatch(palette: Palette, path: Path) -> Path:
    """The palette as an image (its own columns, else 16 squares per row), to show an image
    model the colours."""
    per_row = palette.columns or SWATCH_ROW
    rows = -(-len(palette.colors) // per_row)
    size = (SWATCH * min(per_row, len(palette.colors)), SWATCH * rows)
    img = PILImage.new("RGBA", size, (0, 0, 0, 0))  # a short last row stays transparent
    for i, c in enumerate(palette.colors):
        x, y = (i % per_row) * SWATCH, (i // per_row) * SWATCH
        img.paste((c.r, c.g, c.b, 255), (x, y, x + SWATCH, y + SWATCH))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path
