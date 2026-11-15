from pixelwright.cli import REGISTRY
from pixelwright.core.checks.base import CheckResult, write_report
from pixelwright.workspace import Workspace
from pixelwright.workspace.next_step import STEPS, next_step

IMG = {"image.png": b"png"}


def test_next_step_covers_every_asset_state(ws: Workspace) -> None:
    a = ws.new_asset("hero", "sprite")
    seen = [next_step(a).step]
    (a.path / "inputs").mkdir(exist_ok=True)
    (a.path / "inputs" / "sketch.png").write_bytes(b"s")
    seen.append(next_step(a).step)
    for step in ("generate", "snap", "quantize"):
        a.new_version(step, IMG)
        seen.append(next_step(a).step)
    v = a.new_version("clean", IMG)
    seen.append(next_step(a).step)
    report = a.versions_dir / v / "report.json"
    write_report(report, [CheckResult("orphans", "R-PIX-3", "fail", 3.0)])
    seen.append(next_step(a).step)
    write_report(report, [CheckResult("orphans", "R-PIX-3", "pass", 0.0)])
    a.add_issue("dock", box=(0, 0, 1, 1), version=v)
    seen.append(next_step(a).step)
    a.resolve_issue("dock", v)
    seen.append(next_step(a).step)
    (a.versions_dir / v / "critique.md").write_text("x")
    seen.append(next_step(a).step)
    a.decide(v, "approve")
    seen.append(next_step(a).step)
    a.exported(v, ["out.png"])
    seen.append(next_step(a).step)
    assert seen == [
        "attach",
        "generate",
        "snap",
        "quantize",
        "clean",
        "check",
        "review-checks",
        "fix",
        "critique",
        "approve",
        "export",
        "done",
    ]
    assert set(seen) == set(STEPS)
    for cmd, why in STEPS.values():
        assert cmd.split()[1] in REGISTRY and why
