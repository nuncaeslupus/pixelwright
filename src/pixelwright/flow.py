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
from pixelwright.core.palette import Palette
from pixelwright.core.quantize import discover_palette, quantize_fixed
from pixelwright.core.snap import snap
from pixelwright.io.palette_io import read_palette
from pixelwright.io.png import read_png
from pixelwright.issues import Issue, IssueLog
from pixelwright.project import Project
from pixelwright.rules import raise_check_issues

DISCOVERED_COLORS = 16


@dataclass
class NormalizeResult:
    version: str
    scale: int
    size: tuple[int, int]
    palette: str
    warnings: list[str]


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


def normalize(asset: Asset, source: Path | None = None) -> NormalizeResult:
    """Input → next version: detect the pixel grid, map to the palette, clean stray pixels."""
    if source is None:
        inputs = asset.inputs()
        if not inputs:
            raise AssetError(f"{asset.rel}: no input to normalise; add an image first")
        source = inputs[-1]
    warnings: list[str] = []
    snapped = snap(_rgb(source))
    native = snapped.image
    canvas = asset.settings().canvas
    size = (native.width, native.height)
    if size != (canvas["width"], canvas["height"]):
        warnings.append(
            f"size {size[0]}x{size[1]} differs from the canvas {canvas['width']}x{canvas['height']}"
        )
    palette = asset_palette(asset)
    palette_name = asset.settings().palette
    if palette is None:
        warnings.append(f"palette {palette_name!r} not in style/palettes; colours discovered")
        palette = discover_palette(native, DISCOVERED_COLORS)
        palette_name = "discovered"
    indexed, _ = quantize_fixed(native, palette)
    cleaned, _ = clean(indexed)
    version = asset.add_version(_pil(cleaned))
    if asset.meta().state == "processing":
        asset.set_state("review")
    return NormalizeResult(version, snapped.scale, size, palette_name, warnings)


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
