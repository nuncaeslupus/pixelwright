"""Image providers on the v2 model: a provider is one more input source.

`generate` asks a provider for images, keeps each as an input of the asset and lets the
scripts normalise it into a version. `repaint` inpaints an issue's areas and proposes the
result as a fix. Settings come from `pixelwright.toml`: `[providers.<name>]` (provider
options), `[presets.<name>]` (preamble, negative, scale, params), `[defaults]` (provider
per kind) and `[budget] monthly_usd`. Reference images live in `style/references/`.
"""

from __future__ import annotations

import io
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from pixelwright import flow
from pixelwright.asset import Asset, AssetError
from pixelwright.budget import Ledger, api_key, budget_guard
from pixelwright.core import providers as pv
from pixelwright.core.image import RGBImage
from pixelwright.io.png import encode_png
from pixelwright.issues import IssueLog
from pixelwright.project import Project

DEFAULT_SCALE = 4  # painters work at a multiple of the canvas; normalise brings it back
REFERENCES_DIR = Path("style") / "references"


@dataclass
class GenerateResult:
    provider: str
    mode: str
    prompt: str
    request_hash: str
    estimate_usd: float = 0.0
    cost_usd: float = 0.0
    cache_hit: bool = False
    inputs: list[Path] = field(default_factory=list)
    versions: list[str] = field(default_factory=list)
    fix: str | None = None
    warnings: list[str] = field(default_factory=list)


def provider_config(project: Project, name: str) -> dict[str, Any]:
    cfg = dict(project.extra.get("providers", {}).get(name, {}))
    if cfg.pop("enabled", True) is False:
        raise AssetError(f"provider {name} is disabled in pixelwright.toml")
    if name == "replay":
        cfg["folder"] = str(project.root / cfg.get("folder", "replay"))
    if pv.needs_key(name):
        cfg["api_key"] = api_key(project.root, name)
    return cfg


def default_provider(project: Project, kind: str | None) -> str:
    defaults = project.extra.get("defaults", {})
    return str((kind and defaults.get(kind)) or defaults.get("provider") or "comfyui")


def _preset(project: Project, name: str) -> dict[str, Any]:
    return dict(project.extra.get("presets", {}).get(name, {}))


def _prompt(preset: dict[str, Any], text: str) -> str:
    prompt = " ".join(p for p in (preset.get("preamble", ""), text.strip()) if p)
    if not prompt:
        raise AssetError("say what to paint: a prompt, or a preamble in [presets.<provider>]")
    return prompt


def _provider(asset: Asset, name: str | None) -> tuple[str, pv.Provider]:
    name = name or default_provider(asset.project, asset.settings().kind)
    return name, pv.get(name, **provider_config(asset.project, name))


def generate(
    asset: Asset,
    prompt: str = "",
    *,
    provider: str | None = None,
    mode: str | None = None,
    init: str | None = None,
    n: int = 1,
    seed: int | None = None,
    size: tuple[int, int] | None = None,
    dry_run: bool = False,
    budget_override: bool = False,
) -> GenerateResult:
    """Paint with a provider; each image becomes an input and then a normalised version.

    `init` is `input` (the newest input, the default when there is one), `none`, or a
    version name.
    """
    project = asset.project
    name, prov = _provider(asset, provider)
    preset = _preset(project, name)
    text = _prompt(preset, prompt)
    init_path: Path | None = None
    if init not in (None, "input", "none"):
        init_path = asset.version_path(str(init))
    elif init != "none" and mode in (None, "img2img", "edit") and asset.inputs():
        init_path = asset.inputs()[-1]
    mode = mode or ("img2img" if init_path is not None else "txt2img")
    if mode == "txt2img":
        init_path = None
    if mode == "inpaint":
        raise AssetError("inpaint repaints an issue: pass the issue instead")
    canvas = asset.settings().canvas
    scale = int(preset.get("scale", DEFAULT_SCALE))
    refs = sorted((project.root / REFERENCES_DIR).glob("*.png"))
    palette = flow.asset_palette(asset)
    req = pv.GenRequest(
        mode=mode,
        prompt=text,
        negative=str(preset.get("negative", "")),
        size=size or (canvas["width"] * scale, canvas["height"] * scale),
        init_image=init_path,
        references=tuple(refs[: prov.capabilities.n_references]),
        palette=tuple(c.hex for c in palette.colors)
        if palette and prov.capabilities.palette_input
        else None,
        seed=seed,
        n=n,
        params=dict(preset.get("params", {})),
    )
    pv.check_capability(prov, req)
    out = GenerateResult(name, mode, text, pv.request_hash(name, req))
    if dry_run:
        out.estimate_usd = prov.estimate(req).usd
        return out
    guard = None if budget_override else budget_guard(project.root, project.extra)
    result = pv.run(prov, req, pv.Cache(project.root / "cache"), guard)
    with tempfile.TemporaryDirectory() as tmp:
        for i, data in enumerate(result.images, 1):
            src = Path(tmp) / f"{name}-{result.request_hash[:8]}-{i}.png"
            src.write_bytes(_png(data))
            out.inputs.append(asset.add_input(src))
    for path in out.inputs:
        res = flow.normalize(asset, path)
        flow.run_checks(asset, res.version)
        out.versions.append(res.version)
        out.warnings += res.warnings
    out.cost_usd = 0.0 if result.cache_hit else result.cost.usd
    out.cache_hit = result.cache_hit
    Ledger(project.root).record(name, result, asset=asset.rel, versions=out.versions)
    return out


def _png(data: bytes) -> bytes:
    """Re-encode whatever the provider sent as an RGBA PNG."""
    with Image.open(io.BytesIO(data)) as im:
        rgba = np.asarray(im.convert("RGBA"), dtype=np.uint8)
    return encode_png(RGBImage.from_array(rgba))


def _areas_mask(areas: list[dict[str, Any]], shape: tuple[int, int]) -> np.ndarray:
    if not areas:
        return np.ones(shape, dtype=bool)
    on = np.zeros(shape, dtype=bool)
    for area in areas:
        x, y, w, h = (int(v) for v in area["box"])
        on[y : y + h, x : x + w] = True
    return on


def repaint(
    asset: Asset,
    issue_id: str,
    prompt: str = "",
    *,
    provider: str | None = None,
    seed: int | None = None,
    budget_override: bool = False,
) -> GenerateResult:
    """Inpaint the areas of an issue on its version and propose the result as a fix."""
    project = asset.project
    log = IssueLog(asset)
    issue = log.issue(issue_id)
    with Image.open(asset.version_path(issue.version)) as im:
        base = np.asarray(im.convert("RGBA"), dtype=np.uint8)
    h, w = base.shape[:2]
    region = _areas_mask(issue.areas, (h, w))
    name, prov = _provider(asset, provider)
    preset = _preset(project, name)
    text = _prompt(preset, prompt or issue.message)
    scale = int(preset.get("scale", DEFAULT_SCALE))
    big = np.repeat(np.repeat(base, scale, axis=0), scale, axis=1)
    big_mask = np.repeat(np.repeat(region, scale, axis=0), scale, axis=1)
    with tempfile.TemporaryDirectory() as tmp:
        init, mask = Path(tmp) / "init.png", Path(tmp) / "mask.png"
        init.write_bytes(encode_png(RGBImage.from_array(big)))
        white = np.where(big_mask[..., None], 255, 0).astype(np.uint8).repeat(3, axis=2)
        mask.write_bytes(encode_png(RGBImage.from_array(white)))
        req = pv.GenRequest(
            mode="inpaint",
            prompt=text,
            negative=str(preset.get("negative", "")),
            size=(w * scale, h * scale),
            init_image=init,
            mask=mask,
            seed=seed,
            params=dict(preset.get("params", {})),
        )
        pv.check_capability(prov, req)
        guard = None if budget_override else budget_guard(project.root, project.extra)
        result = pv.run(prov, req, pv.Cache(project.root / "cache"), guard)
    painted = Image.open(io.BytesIO(result.images[0])).convert("RGBA")
    if painted.size != (w * scale, h * scale):
        painted = painted.resize((w * scale, h * scale), Image.Resampling.NEAREST)
    cells = np.asarray(painted)[scale // 2 :: scale, scale // 2 :: scale]
    merged = base.copy()
    merged[region] = cells[region]
    fix = log.propose_fix(issue_id, Image.fromarray(merged, "RGBA"), by="ai")
    out = GenerateResult(name, "inpaint", text, result.request_hash, fix=fix.id)
    out.cost_usd = 0.0 if result.cache_hit else result.cost.usd
    out.cache_hit = result.cache_hit
    Ledger(project.root).record(name, result, asset=asset.rel)
    return out
