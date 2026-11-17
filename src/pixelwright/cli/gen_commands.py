"""Generation commands (M3): generate, regen-region, cost, doctor, next."""

from __future__ import annotations

import io
import json
import platform
import sys
import tempfile
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image as PILImage

from pixelwright.budget import Ledger, api_key, budget_guard, monthly_limit
from pixelwright.cli.commands import region_mask
from pixelwright.cli.flow_commands import generate_v2, is_v2
from pixelwright.cli.registry import EXIT_USAGE, Outcome, Param, PwError, command
from pixelwright.core import providers as pv
from pixelwright.core.image import RGBImage
from pixelwright.io.aseprite_cli import find_aseprite
from pixelwright.io.palette_io import read_palette
from pixelwright.io.png import encode_png, read_png
from pixelwright.project import load_project
from pixelwright.workspace import Asset, Workspace
from pixelwright.workspace.files import sha256_file
from pixelwright.workspace.next_step import next_step
from pixelwright.workspace.style import load_style

IMAGE = "image.png"
DEFAULT_SCALE = 4  # painters work at a multiple of the native canvas; snap brings it back


def _settings(root: Path) -> tuple[Path, dict[str, Any]]:
    """The root and the `pixelwright.toml` tables, for a v2 project or an old workspace."""
    if is_v2(root):
        project = load_project(root)
        return project.root, project.extra
    ws = Workspace.open(root)
    return ws.root, ws.config.extra


def provider_config(ws: Workspace, name: str) -> dict[str, Any]:
    """`[providers.<name>]` from pixelwright.toml, plus the key and defaults it needs."""
    cfg = dict(ws.config.extra.get("providers", {}).get(name, {}))
    if cfg.pop("enabled", True) is False:
        raise PwError("provider_disabled", f"provider {name} is disabled in pixelwright.toml")
    if name == "replay":
        cfg["folder"] = str(ws.root / cfg.get("folder", "replay"))
    if pv.needs_key(name):
        cfg["api_key"] = api_key(ws.root, name)
    return cfg


def default_provider(ws: Workspace, kind: str) -> str:
    defaults = ws.config.extra.get("defaults", {})
    return str(defaults.get(kind) or defaults.get("provider") or "comfyui")


def _sketch(asset: Asset) -> Path | None:
    found = sorted((asset.path / "inputs").glob("sketch.*"))
    return found[0] if found else None


def _png_bytes(data: bytes) -> bytes:
    """Re-encode whatever the provider sent as an RGBA PNG (stable bytes, one format)."""
    with PILImage.open(io.BytesIO(data)) as im:
        rgba = np.asarray(im.convert("RGBA"), dtype=np.uint8)
    return encode_png(RGBImage.from_array(rgba))


def _size(text: str | None, canvas: dict[str, int], scale: int) -> tuple[int, int]:
    if text:
        try:
            w, h = (int(v) for v in text.lower().split("x"))
        except ValueError:
            raise PwError("invalid", f"size must be WIDTHxHEIGHT, got {text!r}") from None
        return w, h
    return canvas["width"] * scale, canvas["height"] * scale


@command(
    "cost",
    "money spent on providers this month, against the workspace budget",
    Param("month", help="month YYYY-MM (default: this month)"),
    Param("by", help="group rows by", choices=("provider", "asset")),
)
def cmd_cost(root: Path, a: dict[str, Any]) -> Outcome:
    root, settings = _settings(root)
    month = a["month"] or datetime.now(UTC).strftime("%Y-%m")
    if len(month) != 7 or month[4] != "-":
        raise PwError("invalid", f"month must be YYYY-MM, got {month!r}")
    ledger = Ledger(root)
    rows = ledger.rows(month)
    data: dict[str, Any] = {
        "month": month,
        "spent_usd": ledger.spent(month),
        "limit_usd": monthly_limit(settings),
        "calls": len(rows),
        "cache_hits": sum(1 for r in rows if r["cache_hit"]),
    }
    if a["by"]:
        groups: dict[str, float] = defaultdict(float)
        for r in rows:
            groups[str(r[a["by"]] or "-")] += float(r["cost_usd"])
        data["rows"] = [{a["by"]: k, "cost_usd": round(v, 6)} for k, v in sorted(groups.items())]
    else:
        data["rows"] = rows
    return Outcome(data=data)


@command(
    "generate",
    "paint candidate versions with an image provider (the style preset shapes the request)",
    Param("asset", help="asset id, or asset path in a v2 project", required=True, positional=True),
    Param("provider", help="provider name (default: [defaults] in pixelwright.toml)"),
    Param("mode", help="what to send", choices=pv.MODES),
    Param("prompt", help="what to paint (added after the style preamble)", default=""),
    Param("prompt_file", help="read the prompt from this file"),
    Param("init", help="init image: `sketch` (v2: `input`), `none` or a version"),
    Param("n", "int", help="candidates, 1-4", default=1),
    Param("seed", "int", help="seed, for reproducible calls"),
    Param("size", help="generation size WIDTHxHEIGHT (default: canvas x 4)"),
    Param("experiment", "bool", help="keep the results as experiments, not drafts"),
    Param("dry_run", "bool", help="show the request hash and estimated cost; send nothing"),
    Param("budget_override", "bool", help="allow this call to pass the monthly budget"),
    Param("issue", help="v2 project: repaint this issue's areas and propose it as a fix"),
)
def cmd_generate(root: Path, a: dict[str, Any]) -> Outcome:
    if is_v2(root):
        out: Outcome = generate_v2(root, a)
        return out
    ws = Workspace.open(root)
    asset = ws.asset(a["asset"])
    spec = asset.spec()
    name = a["provider"] or default_provider(ws, spec["kind"])
    provider = pv.get(name, **provider_config(ws, name))
    style = load_style(ws.path("style"))
    preset: dict[str, Any] = dict(style.presets.get(name, {}))
    prompt = Path(a["prompt_file"]).read_text(encoding="utf-8") if a["prompt_file"] else a["prompt"]
    prompt = " ".join(p for p in (preset.get("preamble", ""), prompt.strip()) if p)
    if not prompt:
        raise PwError("invalid", "generate needs --prompt, --prompt-file or a style preamble")

    init: Path | None = None
    if a["init"] and a["init"] != "sketch":
        init = asset.versions_dir / a["init"] / IMAGE
        if not init.is_file():
            raise PwError("version_not_found", f"{asset.id} has no version {a['init']}")
    elif a["init"] == "sketch" or a["mode"] in (None, "img2img", "edit"):
        init = _sketch(asset)
        if init is None and a["init"] == "sketch":
            raise PwError("not_found", f"{asset.id} has no sketch; run `pw attach --as sketch`")
    mode = a["mode"] or ("img2img" if init is not None else "txt2img")
    if mode == "txt2img":
        init = None
    if mode == "inpaint":
        raise PwError("invalid", "inpaint goes through `pw regen-region`", exit_code=EXIT_USAGE)

    refs = [ws.path("style") / r for r in style.references if (ws.path("style") / r).is_file()]
    refs += sorted((asset.path / "inputs" / "refs").glob("*.png"))
    palette = None
    if spec.get("palette") and provider.capabilities.palette_input:
        pal = read_palette(ws.path("style") / str(spec["palette"]).removeprefix("style:"))
        palette = tuple(c.hex for c in pal.colors)
    scale = int(preset.get("scale", DEFAULT_SCALE))
    req = pv.GenRequest(
        mode=mode,
        prompt=prompt,
        negative=str(preset.get("negative", "")),
        size=_size(a["size"], spec["canvas"], scale),
        init_image=init,
        references=tuple(refs[: provider.capabilities.n_references]),
        palette=palette,
        seed=a["seed"],
        n=a["n"],
        params=dict(preset.get("params", {})),
    )
    pv.check_capability(provider, req)
    key = pv.request_hash(name, req)
    if a["dry_run"]:
        estimate = provider.estimate(req).usd
        return Outcome(
            asset.id,
            data={
                "provider": name,
                "mode": mode,
                "prompt": prompt,
                "request_hash": key,
                "estimate_usd": estimate,
                "size": list(req.size),
            },
        )

    guard = None if a["budget_override"] else budget_guard(ws.root, ws.config.extra)
    result = pv.run(provider, req, pv.Cache(ws.path("cache")), guard)
    inputs = {"init": sha256_file(init)} if init is not None else {}
    stage = "experiment" if a["experiment"] else "draft"
    per_image = round(result.cost.usd / max(1, len(result.images)), 6)
    versions = []
    for image in result.images:
        versions.append(
            asset.new_version(
                "generate",
                {IMAGE: _png_bytes(image)},
                params={"mode": mode, "prompt": prompt, "n": req.n, "size": list(req.size)},
                inputs=inputs,
                stage=stage,
                provider=name,
                model=result.model,
                request_hash=result.request_hash,
                seed=result.seed,
                cost_usd=0.0 if result.cache_hit else per_image,
                cache_hit=result.cache_hit,
                licence=provider.capabilities.licence_note,
            )
        )
    Ledger(ws.root).record(name, result, asset=asset.id, versions=versions)
    last = versions[-1]
    return Outcome(
        asset.id,
        last,
        asset.stage(last),
        [(asset.versions_dir / v / IMAGE).relative_to(ws.root).as_posix() for v in versions],
        {
            "versions": versions,
            "provider": name,
            "mode": mode,
            "request_hash": key,
            "cost_usd": 0.0 if result.cache_hit else result.cost.usd,
            "cache_hit": result.cache_hit,
        },
    )


def _check(name: str, ok: bool, detail: str, fix: str = "") -> dict[str, Any]:
    return {"check": name, "ok": ok, "detail": detail, "fix": "" if ok else fix}


def _comfyui_row(settings: dict[str, Any]) -> dict[str, Any]:
    cfg = settings.get("providers", {}).get("comfyui", {})
    url = str(cfg.get("base_url", "http://127.0.0.1:8188")).rstrip("/")
    try:
        with urllib.request.urlopen(url + "/system_stats", timeout=2) as resp:
            stats = json.loads(resp.read() or b"{}")
        gpus = [d.get("name", "?") for d in stats.get("devices", [])]
        return _check("comfyui", True, f"running at {url}; devices: {', '.join(gpus) or '-'}")
    except (OSError, ValueError):
        return _check(
            "comfyui",
            False,
            f"not answering at {url}",
            "start ComfyUI (python main.py in its folder) or set [providers.comfyui] base_url; "
            "see docs/guide/comfyui.md",
        )


@command(
    "doctor",
    "check what pixelwright needs: Python, Aseprite, providers and their keys, budget",
    Param("offline", "bool", help="skip the checks that use the network (ComfyUI)"),
)
def cmd_doctor(root: Path, a: dict[str, Any]) -> Outcome:
    root, settings = _settings(root)
    rows = [
        _check(
            "python", sys.version_info >= (3, 12), platform.python_version(), "use Python 3.12+"
        ),
    ]
    ase = find_aseprite()
    rows.append(
        _check(
            "aseprite",
            ase is not None,
            str(ase or "not found"),
            "install Aseprite or set PW_ASEPRITE to its binary (only for `pw ase`)",
        )
    )
    for name in pv.names():
        if name == "comfyui":
            if not a["offline"]:
                rows.append(_comfyui_row(settings))
            continue
        if pv.needs_key(name):
            try:
                api_key(root, name)
                rows.append(_check(name, True, "key found"))
            except pv.ProviderError as err:
                rows.append(_check(name, False, "no key", err.message))
    month = datetime.now(UTC).strftime("%Y-%m")
    spent, limit = Ledger(root).spent(month), monthly_limit(settings)
    rows.append(
        _check(
            "budget",
            spent < limit,
            f"{spent:.2f} of {limit:.2f} USD spent in {month}",
            "raise [budget] monthly_usd in pixelwright.toml, or wait for next month",
        )
    )
    lines = []
    for r in rows:
        mark = "ok  " if r["ok"] else "fix "
        lines.append(f"{mark}{r['check']:<16} {r['detail']}")
        if r["fix"]:
            lines.append(f"     {'':<16} -> {r['fix']}")
    failing = sum(1 for r in rows if not r["ok"])
    lines.append(
        "" if not failing else f"\n{failing} to fix; the rest of pixelwright works without them."
    )
    return Outcome(data={"rows": rows, "failing": failing}, text="\n".join(lines).rstrip())


@command(
    "next",
    "what to do next with an asset, and why (or with each asset when none is given)",
    Param("asset", help="asset id (default: every asset)", positional=True),
)
def cmd_next(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    assets = [ws.asset(a["asset"])] if a["asset"] else [ws.asset(i) for i in ws.assets()]
    steps = [{"asset": x.id, **next_step(x).to_dict()} for x in assets]
    if not steps:
        text = "No assets yet. Start one:\n  pw new <id> --kind background --canvas 320x180"
        return Outcome(data={"steps": []}, text=text)
    text = "\n\n".join(f"{s['asset']}: {s['step']}\n  {s['command']}\n  {s['why']}" for s in steps)
    first = steps[0]
    return Outcome(
        first["asset"] if a["asset"] else None,
        first["version"],
        data={"steps": steps, **(first if a["asset"] else {})},
        text=text,
    )


@command(
    "regen-region",
    "repaint only an issue's region with a provider that can inpaint, and resolve the issue",
    Param("asset", help="asset id", required=True, positional=True),
    Param("issue", help="issue id whose region to repaint", required=True),
    Param("version", help="version to repaint (default: the issue's version, else latest)"),
    Param("provider", help="provider name (default: [defaults] in pixelwright.toml)"),
    Param("prompt", help="what to paint in the region", default=""),
    Param("seed", "int", help="seed, for reproducible calls"),
    Param("keep_open", "bool", help="do not mark the issue fixed by the new version"),
    Param("budget_override", "bool", help="allow this call to pass the monthly budget"),
)
def cmd_regen_region(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    asset = ws.asset(a["asset"])
    entry = asset.issue(a["issue"])
    version = a["version"] or entry.get("version") or asset.latest()
    if version is None or not (asset.versions_dir / version / IMAGE).is_file():
        raise PwError("version_not_found", f"{asset.id} has no version {version}")
    base = read_png(asset.versions_dir / version / IMAGE).to_rgba()
    h, w = base.shape[:2]
    region = region_mask(asset, entry, (h, w))
    if not region.any():
        raise PwError("invalid", f"issue {entry['id']} has an empty region")

    name = a["provider"] or default_provider(ws, asset.spec()["kind"])
    provider = pv.get(name, **provider_config(ws, name))
    preset: dict[str, Any] = dict(load_style(ws.path("style")).presets.get(name, {}))
    note = entry.get("note", "")
    prompt = " ".join(p for p in (preset.get("preamble", ""), a["prompt"] or note) if p)
    if not prompt:
        raise PwError("invalid", "regen-region needs --prompt (the issue has no note)")
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
            prompt=prompt,
            negative=str(preset.get("negative", "")),
            size=(w * scale, h * scale),
            init_image=init,
            mask=mask,
            seed=a["seed"],
            params=dict(preset.get("params", {})),
        )
        pv.check_capability(provider, req)
        guard = None if a["budget_override"] else budget_guard(ws.root, ws.config.extra)
        result = pv.run(provider, req, pv.Cache(ws.path("cache")), guard)
        inputs = {"init": sha256_file(init), "mask": sha256_file(mask)}
    painted = PILImage.open(io.BytesIO(result.images[0])).convert("RGBA")
    if painted.size != (w * scale, h * scale):
        painted = painted.resize((w * scale, h * scale), PILImage.Resampling.NEAREST)
    cells = np.asarray(painted)[scale // 2 :: scale, scale // 2 :: scale]
    out = base.copy()
    out[region] = cells[region]
    new = asset.new_version(
        "regen-region",
        {IMAGE: encode_png(RGBImage.from_array(out))},
        params={"issue": entry["id"], "prompt": prompt, "scale": scale},
        parent=version,
        inputs=inputs,
        provider=name,
        model=result.model,
        request_hash=result.request_hash,
        seed=result.seed,
        cost_usd=0.0 if result.cache_hit else result.cost.usd,
        cache_hit=result.cache_hit,
        licence=provider.capabilities.licence_note,
    )
    Ledger(ws.root).record(name, result, asset=asset.id, versions=[new])
    if not a["keep_open"]:
        asset.resolve_issue(entry["id"], new, author="claude")
    changed = int((out != base).any(axis=-1).sum())
    path = (asset.versions_dir / new / IMAGE).relative_to(ws.root).as_posix()
    return Outcome(
        asset.id,
        new,
        asset.stage(new),
        [path],
        {"issue": entry["id"], "parent": version, "changed": changed, "provider": name},
    )
