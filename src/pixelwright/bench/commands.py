"""`pw bench`: run the provider benchmark in a project (estimate first, spend on --yes).

Each (brief, provider) is an asset `bench/<brief>/<provider>`; the provider paints the
samples (kept as inputs), each chain post-processes every sample into a version, and the
pixel checks score it. Results go to `benchmarks/<name>/scores.json`. A rerun skips what
is already scored and replays cached requests, so an interrupted run resumes for free.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from pixelwright.asset import Asset, open_asset
from pixelwright.bench.matrix import Brief, Matrix, load_matrix
from pixelwright.bench.rank import READERS, WINNERS, items, next_pair, ranking, record
from pixelwright.bench.report import write_report
from pixelwright.budget import Ledger, month_of, monthly_limit
from pixelwright.cli.registry import Outcome, Param, PwError, command
from pixelwright.core import providers as pv
from pixelwright.core.checks import check_banding, check_line_runs, check_orphans
from pixelwright.core.clean import clean
from pixelwright.core.image import IndexedImage, RGBImage
from pixelwright.core.providers.base import EXIT_BUDGET
from pixelwright.core.quantize import discover_palette, quantize_fixed
from pixelwright.core.snap import snap
from pixelwright.flow import asset_name, asset_palette
from pixelwright.generate import DEFAULT_SCALE, generate, provider_config
from pixelwright.project import CATEGORY_FILE, Project, ProjectError, load_project
from pixelwright.workspace.files import write_bytes_atomic, write_toml

BENCH = "bench"


def asset_rel(brief: str, provider: str) -> str:
    return f"{BENCH}/{asset_name(brief)}/{asset_name(provider)}"


def estimate(project: Project, m: Matrix) -> list[dict[str, Any]]:
    """One row per (brief, provider): calls, estimated USD, and why it cannot run."""
    rows = []
    for brief in m.briefs:
        w, _, h = brief.canvas.partition("x")
        for name in m.providers:
            row: dict[str, Any] = {"brief": brief.id, "provider": name, "images": m.samples}
            try:
                cfg = provider_config(project, name)
                problem = ""
            except (ValueError, pv.ProviderError) as exc:
                cfg, problem = {"api_key": "missing"}, str(exc)
            provider = pv.get(name, **cfg)
            req = pv.GenRequest(
                mode="txt2img",
                prompt=brief.prompt,
                size=(int(w) * DEFAULT_SCALE, int(h) * DEFAULT_SCALE),
                n=m.samples,
                seed=m.seed,
            )
            row["usd"] = round(provider.estimate(req).usd, 4)
            row["problem"] = problem
            rows.append(row)
    return rows


def _table(rows: list[dict[str, Any]], total: float) -> str:
    lines = [f"{'brief':<14}{'provider':<18}{'images':>7}{'usd':>9}  note"]
    for r in rows:
        line = (
            f"{r['brief']:<14}{r['provider']:<18}{r['images']:>7}{r['usd']:>9.3f}  {r['problem']}"
        )
        lines.append(line.rstrip())
    lines.append(f"{'total':<32}{sum(r['images'] for r in rows):>7}{total:>9.3f}")
    return "\n".join(lines)


def _bench_asset(project: Project, brief: Brief, provider: str) -> Asset:
    """`assets/bench/<brief>/` holds the brief's canvas and palette for every provider."""
    rel = asset_rel(brief.id, provider)
    path = project.assets_dir / rel
    if (path / "asset.toml").is_file():
        return open_asset(project, path)
    folder = path.parent
    folder.mkdir(parents=True, exist_ok=True)
    w, _, h = brief.canvas.partition("x")
    layer: dict[str, Any] = {"kind": brief.kind, "canvas": {"width": int(w), "height": int(h)}}
    if brief.palette:
        layer["palette"] = Path(brief.palette).stem
    write_toml(folder / CATEGORY_FILE, layer)
    asset = Asset.create(project, rel)
    if brief.sketch is not None:
        asset.add_input(brief.sketch)
    return asset


Pixels = RGBImage | IndexedImage


def _chain(asset: Asset, source: Path, steps: tuple[str, ...], colors: int) -> Pixels:
    with Image.open(source) as im:
        image: Pixels = RGBImage.from_array(np.asarray(im.convert("RGBA")))
    palette = asset_palette(asset)
    for step in steps:
        if step == "snap":
            image = snap(image if isinstance(image, RGBImage) else image.to_rgb_image()).image
        elif step == "quantize":
            rgb = image if isinstance(image, RGBImage) else image.to_rgb_image()
            image, _ = quantize_fixed(rgb, palette or discover_palette(rgb, colors))
        elif step == "clean":
            if isinstance(image, RGBImage):
                image, _ = quantize_fixed(image, palette or discover_palette(image, colors))
            image, _ = clean(image)
    return image


def _score(image: Pixels, colors: int) -> list[dict[str, Any]]:
    if isinstance(image, RGBImage):
        image, _ = quantize_fixed(image, discover_palette(image, colors))
    found = (check_orphans(image), check_line_runs(image), check_banding(image))
    return [r.to_dict() for r in found]


def run_matrix(project: Project, m: Matrix, out: Path) -> list[dict[str, Any]]:
    scores_path = out / "scores.json"
    scores: list[dict[str, Any]] = (
        json.loads(scores_path.read_text(encoding="utf-8")) if scores_path.is_file() else []
    )
    done = {(s["brief"], s["provider"], s["sample"], s["chain"]) for s in scores}
    for brief in m.briefs:
        for name in m.providers:
            asset = _bench_asset(project, brief, name)
            gen = generate(
                asset, brief.prompt, provider=name, init=None if brief.sketch else "none",
                n=m.samples, seed=m.seed, normalize=False,
            )  # fmt: skip
            per_image = gen.cost_usd / max(1, len(gen.inputs))
            for sample, source in enumerate(gen.inputs):
                for chain, steps in m.chains.items():
                    if (brief.id, name, sample, chain) in done:
                        continue
                    image = _chain(asset, source, steps, m.colors)
                    version = asset.add_version(
                        Image.fromarray(np.ascontiguousarray(image.to_rgba()), "RGBA")
                    )
                    results = _score(image, m.colors)
                    scores.append(
                        {
                            "brief": brief.id,
                            "provider": name,
                            "sample": sample,
                            "chain": chain,
                            "asset": asset.rel,
                            "input": source.name,
                            "version": version,
                            "cost_usd": per_image,
                            "fails": sum(r["status"] == "fail" for r in results),
                            "warns": sum(r["status"] == "warn" for r in results),
                            "checks": {r["check"]: [r["status"], r["value"]] for r in results},
                        }
                    )
                    write_bytes_atomic(scores_path, json.dumps(scores, indent=1).encode())
    return scores


ACTIONS = ("run", "pair", "vote", "rank", "report", "apply")


def bench_dir(root: Path, name: str | None) -> Path:
    base = root / "benchmarks"
    if name:
        out = base / name
    else:
        found = sorted(base.glob("*/scores.json"), key=lambda p: p.stat().st_mtime)
        if not found:
            raise PwError("not_found", "no benchmark results; run `pw bench run --yes` first")
        out = found[-1].parent
    if not (out / "scores.json").is_file():
        raise PwError("not_found", f"no scores in {out}")
    return out


def _after_run(project: Project, a: dict[str, Any]) -> Outcome:
    out = bench_dir(project.root, a["name"])
    act = a["action"]
    if act == "pair":
        pair = next_pair(out, a["reader"])
        text = "No pairs left to vote on." if pair is None else json.dumps(pair, indent=1)
        return Outcome(data={"pair": pair, "name": out.name}, text=text)
    if act == "vote":
        if not (a["a"] and a["b"] and a["winner"]):
            raise PwError("invalid", "bench vote needs --a, --b and --winner")
        vote = record(out, a["reader"], a["a"], a["b"], a["winner"], a["note"])
        return Outcome(data={"vote": vote, "next": next_pair(out, a["reader"])})
    tables = {r: ranking(out, r) for r in (*READERS, None)}
    if act == "rank":
        text = "\n".join(
            f"{i + 1}. {r['system']:<32} {r['strength']:.3f}  ({r['games']} votes, "
            f"{r['mean_fails']} failing checks on average)"
            for i, r in enumerate(tables[None])
        )
        return Outcome(
            data={"ranking": tables[None], "human": tables["human"], "claude": tables["claude"]},
            text=text,
        )
    if act == "report":
        path = write_report(out, tables)
        rel = path.relative_to(project.root).as_posix()
        return Outcome(outputs=[rel], data={"report": rel}, text=f"Report: {path}")
    # apply: the strongest system's provider becomes the default for each kind benchmarked
    best = tables["human"] if any(r["games"] for r in tables["human"]) else tables[None]
    kinds = sorted({_kind(project, r) for r in items(out)})
    defaults = dict(project.extra.get("defaults", {}))
    for kind in kinds:
        defaults[kind] = best[0]["provider"]
    project.extra["defaults"] = defaults
    write_toml(project.root / "pixelwright.toml", project.to_dict())
    return Outcome(
        data={"defaults": defaults, "from": best[0]["system"]},
        text=f"[defaults] now: {defaults} (from {best[0]['system']})",
    )


def _kind(project: Project, row: dict[str, Any]) -> str:
    asset = open_asset(project, project.assets_dir / row["asset"])
    return asset.settings().kind or "background"


@command(
    "bench",
    "provider benchmark: run (estimate; --yes spends), pair/vote, rank, report, apply",
    Param("action", help="what to do", required=True, positional=True, choices=ACTIONS),
    Param("matrix", help="matrix.yaml (providers x chains x briefs x samples)"),
    Param("yes", "bool", help="send the requests (paid providers cost money)"),
    Param("name", help="benchmark name under benchmarks/ (default: the only or newest one)"),
    Param("reader", help="who votes", choices=READERS, default="claude"),
    Param("a", help="vote: token of image A"),
    Param("b", help="vote: token of image B"),
    Param("winner", help="vote: the better image", choices=WINNERS),
    Param("note", help="vote: why", default=""),
)
def cmd_bench(root: Path, a: dict[str, Any]) -> Outcome:
    try:
        project = load_project(root)
    except ProjectError as exc:
        raise PwError("no_project", f"{exc}; the benchmark runs in a project (pw init)") from exc
    if a["action"] != "run":
        return _after_run(project, a)
    if not a["matrix"]:
        raise PwError("invalid", "bench run needs --matrix <matrix.yaml>")
    m = load_matrix(Path(a["matrix"]))
    rows = estimate(project, m)
    total = round(sum(r["usd"] for r in rows), 4)
    out = project.root / "benchmarks" / m.name
    data: dict[str, Any] = {"estimate_usd": total, "rows": rows, "sent": 0, "out": str(out)}
    text = _table(rows, total)
    if not a["yes"]:
        text += "\n\nNothing sent. Run again with --yes to spend this."
        return Outcome(data=data, text=text)
    blocked = [r for r in rows if r["problem"]]
    if blocked:
        raise PwError("not_ready", "fix these first:\n" + text)
    if total > m.max_usd:
        raise PwError(
            "budget_exceeded",
            f"estimate {total} USD is over the matrix cap {m.max_usd} USD",
            exit_code=EXIT_BUDGET,
        )
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    left = monthly_limit(project.extra) - Ledger(project.root).spent(month_of(now))
    if total > left:
        raise PwError(
            "budget_exceeded",
            f"estimate {total} USD is over the {left:.2f} USD left this month",
            exit_code=EXIT_BUDGET,
        )
    out.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(out / "matrix.yaml", Path(a["matrix"]).read_bytes())
    scores = run_matrix(project, m, out)
    data.update(sent=len(scores), scores=str(out / "scores.json"))
    return Outcome(
        outputs=[(out / "scores.json").relative_to(project.root).as_posix()],
        data=data,
        text=text + f"\n\n{len(scores)} results scored: {out / 'scores.json'}",
    )
