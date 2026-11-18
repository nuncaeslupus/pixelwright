"""Generation commands: generate (images from a provider), cost, doctor."""

from __future__ import annotations

import json
import platform
import sys
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pixelwright.budget import Ledger, api_key, monthly_limit
from pixelwright.cli.flow_commands import _project, generate_v2
from pixelwright.cli.registry import Outcome, Param, PwError, command
from pixelwright.core import providers as pv
from pixelwright.io.aseprite_cli import find_aseprite


def _settings(root: Path) -> tuple[Path, dict[str, Any]]:
    """The project root and the other tables of `pixelwright.toml`."""
    project = _project(root)
    return project.root, project.extra


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
    "paint with an image provider: images become inputs, then normalised versions",
    Param("asset", help="asset path, e.g. scenes/harbour", required=True, positional=True),
    Param("provider", help="provider name (default: [defaults] in pixelwright.toml)"),
    Param("mode", help="what to send", choices=pv.MODES),
    Param("prompt", help="what to paint (after the [presets] preamble)", default=""),
    Param("prompt_file", help="read the prompt from this file"),
    Param("init", help="start from `input` (the newest, default), `none` or a version"),
    Param("n", "int", help="candidates, 1-4", default=1),
    Param("seed", "int", help="seed, for reproducible calls"),
    Param("size", help="generation size WIDTHxHEIGHT (default: canvas x 4)"),
    Param("dry_run", "bool", help="show the request hash and estimated cost; send nothing"),
    Param("budget_override", "bool", help="allow this call to pass the monthly budget"),
    Param("issue", help="repaint this issue's areas and propose the result as a fix"),
    Param("scene", help="match this scene's camera, horizon and scale (with --at)"),
    Param("at", "float", help="with --scene: row where the object stands"),
    Param("height", "float", help="with --scene: the prop's height in px (default: a person)"),
)
def cmd_generate(root: Path, a: dict[str, Any]) -> Outcome:
    out: Outcome = generate_v2(root, a)
    return out


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
