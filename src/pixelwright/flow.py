"""The steps of the flow on the v2 project model: normalise, check, and what comes next.

Scripts always run first (normalise, check); the AI and the person act on the issues.
`next_step` names the single next step of an asset and who owes it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image as PILImage

from pixelwright.asset import Asset, AssetError
from pixelwright.core.checks import CheckResult, check_banding, check_line_runs, check_orphans
from pixelwright.core.clean import clean
from pixelwright.core.image import IndexedImage, RGBImage
from pixelwright.core.importance import ColorGroup, analyze_colors, importance_map
from pixelwright.core.palette import Palette
from pixelwright.core.quantize import discover_palette, quantize_fixed
from pixelwright.core.snap import snap
from pixelwright.io.palette_io import read_palette
from pixelwright.io.png import read_png
from pixelwright.issues import Issue, IssueLog
from pixelwright.project import Project
from pixelwright.rules import raise_check_issues

DISCOVERED_COLORS = 16  # plus up to MAX_ACCENTS kept for small important colours
PROTECT = 0.8  # pixels at least this important are never cleaned away
OVERSIZE = 1.25  # a snapped image this much larger than the canvas has no real pixel grid


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


def reduce_to_canvas(image: RGBImage, canvas: tuple[int, int]) -> RGBImage:
    """Scale an image without a usable pixel grid (a painting, a photo) down to fit the
    canvas, keeping its aspect ratio; each new pixel is the area average of the old ones."""
    factor = min(canvas[0] / image.width, canvas[1] / image.height)
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
    snapped = snap(source_rgb)
    canvas = asset.settings().canvas
    cw, ch = canvas["width"], canvas["height"]
    native = snapped.image
    if native.width > cw * OVERSIZE and native.height > ch * OVERSIZE:
        small = reduce_to_canvas(source_rgb, (cw, ch))
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


def normalize(asset: Asset, source: Path | None = None) -> NormalizeResult:
    """Input → next version: pixel grid (or reduce to the canvas), palette, stray pixels."""
    prep = prepare(asset, source)
    native, warnings = prep.image, list(prep.warnings)
    imp = importance_map(native)
    palette = asset_palette(asset)
    palette_name = asset.settings().palette
    if palette is None:
        warnings.append(f"palette {palette_name!r} not in style/palettes; colours discovered")
        palette = discover_palette(native, DISCOVERED_COLORS, importance=imp)
        palette_name = "discovered"
    indexed, _ = quantize_fixed(native, palette)
    # a lone pixel that stands out strongly (a star, a glint) is meant, not noise
    cleaned, _ = clean(indexed, imp < PROTECT)
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
        colors = {tuple(c) for c in native.rgba[..., :3].reshape(-1, 3).tolist()}
        palette = discover_palette(native, max(1, min(len(colors), 256)))
    indexed, _ = quantize_fixed(native, palette)
    results = [check_orphans(indexed), check_line_runs(indexed), check_banding(indexed)]
    issues = raise_check_issues(IssueLog(asset), version, results)
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
