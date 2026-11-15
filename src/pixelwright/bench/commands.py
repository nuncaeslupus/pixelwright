"""`pw bench`: run the provider benchmark in the workspace (estimate first, spend on --yes).

Each (brief, provider) is an asset `bench-<brief>-<provider>`; `generate` makes the
samples, each chain post-processes every sample, `check` scores the result. Results go to
`benchmarks/<name>/scores.json`. A rerun skips what is already scored and replays cached
requests, so an interrupted run resumes for free.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pixelwright.bench.matrix import Matrix, load_matrix
from pixelwright.cli.gen_commands import DEFAULT_SCALE, provider_config
from pixelwright.cli.registry import REGISTRY, Outcome, Param, PwError, command
from pixelwright.core import providers as pv
from pixelwright.core.providers.base import EXIT_BUDGET
from pixelwright.workspace import Workspace
from pixelwright.workspace.asset import utc_now
from pixelwright.workspace.budget import Ledger, month_of, monthly_limit
from pixelwright.workspace.files import write_bytes_atomic


def asset_id(brief: str, provider: str) -> str:
    return f"bench-{brief}-{provider}"


def estimate(ws: Workspace, m: Matrix) -> list[dict[str, Any]]:
    """One row per (brief, provider): calls, estimated USD, and why it cannot run."""
    rows = []
    for brief in m.briefs:
        w, _, h = brief.canvas.partition("x")
        for name in m.providers:
            row: dict[str, Any] = {"brief": brief.id, "provider": name, "images": m.samples}
            try:
                cfg = provider_config(ws, name)
                problem = ""
            except (PwError, pv.ProviderError) as exc:
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


def _pw(root: Path, name: str, **args: Any) -> Outcome:
    cmd = REGISTRY[name]
    full = {p.name: args.get(p.name, [] if p.kind == "list" else p.default) for p in cmd.params}
    return cmd.run(root, full)


def run_matrix(ws: Workspace, m: Matrix, out: Path) -> list[dict[str, Any]]:
    scores_path = out / "scores.json"
    scores: list[dict[str, Any]] = (
        json.loads(scores_path.read_text(encoding="utf-8")) if scores_path.is_file() else []
    )
    done = {(s["brief"], s["provider"], s["sample"], s["chain"]) for s in scores}
    for brief in m.briefs:
        for name in m.providers:
            aid = asset_id(brief.id, name)
            if aid not in ws.assets():
                _pw(
                    ws.root,
                    "new",
                    asset=aid,
                    kind=brief.kind,
                    canvas=brief.canvas,
                    palette=brief.palette,
                )
                if brief.sketch is not None:
                    _pw(ws.root, "attach", asset=aid, file=str(brief.sketch), **{"as": "sketch"})
            gen = _pw(
                ws.root,
                "generate",
                asset=aid,
                provider=name,
                prompt=brief.prompt,
                n=m.samples,
                seed=m.seed,
            )
            for sample, version in enumerate(gen.data["versions"]):
                for chain, steps in m.chains.items():
                    if (brief.id, name, sample, chain) in done:
                        continue
                    current = version
                    for step in steps:
                        extra = (
                            {"discover": m.colors}
                            if step == "quantize" and not brief.palette
                            else {}
                        )
                        current = str(
                            _pw(ws.root, step, asset=aid, version=current, **extra).version
                        )
                    checked = _pw(ws.root, "check", asset=aid, version=current)
                    results = checked.data["results"]
                    scores.append(
                        {
                            "brief": brief.id,
                            "provider": name,
                            "sample": sample,
                            "chain": chain,
                            "asset": aid,
                            "generated": version,
                            "version": current,
                            "cost_usd": gen.data["cost_usd"] / max(1, len(gen.data["versions"])),
                            "fails": sum(r["status"] == "fail" for r in results),
                            "warns": sum(r["status"] == "warn" for r in results),
                            "checks": {r["check"]: [r["status"], r["value"]] for r in results},
                        }
                    )
                    write_bytes_atomic(scores_path, json.dumps(scores, indent=1).encode())
    return scores


@command(
    "bench",
    "provider benchmark: `run` shows the cost estimate, and spends only with --yes",
    Param("action", help="what to do", required=True, positional=True, choices=("run",)),
    Param("matrix", help="matrix.yaml (providers x chains x briefs x samples)"),
    Param("yes", "bool", help="send the requests (paid providers cost money)"),
)
def cmd_bench(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    if not a["matrix"]:
        raise PwError("invalid", "bench run needs --matrix <matrix.yaml>")
    m = load_matrix(Path(a["matrix"]))
    rows = estimate(ws, m)
    total = round(sum(r["usd"] for r in rows), 4)
    out = ws.root / "benchmarks" / m.name
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
    left = monthly_limit(ws.config) - Ledger(ws.root).spent(month_of(utc_now()))
    if total > left:
        raise PwError(
            "budget_exceeded",
            f"estimate {total} USD is over the {left:.2f} USD left this month",
            exit_code=EXIT_BUDGET,
        )
    out.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(out / "matrix.yaml", Path(a["matrix"]).read_bytes())
    scores = run_matrix(ws, m, out)
    data.update(sent=len(scores), scores=str(out / "scores.json"))
    return Outcome(
        outputs=[(out / "scores.json").relative_to(ws.root).as_posix()],
        data=data,
        text=text + f"\n\n{len(scores)} results scored: {out / 'scores.json'}",
    )
