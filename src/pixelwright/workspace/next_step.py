"""What to do next with an asset, in plain words (`pw next`).

The pipeline an asset goes through: sketch -> generate -> snap -> quantize -> clean ->
check -> critique -> fix issues -> approve -> export. This module reads where an asset is
and names the one next step, the command for it and why.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from pixelwright.core.checks.base import read_report
from pixelwright.workspace.asset import Asset

# Every step's command (the registry name is the first word after `pw`).
STEPS: dict[str, tuple[str, str]] = {
    "attach": (
        "pw attach {id} <sketch.png> --as sketch",
        "Start from your sketch: the painter follows its shapes. "
        "(Or attach any image as a first version without --as.)",
    ),
    "generate": (
        'pw generate {id} --prompt "<what to paint>" --n 2',
        "An image model paints candidates from the sketch and the style guide. "
        "They look like pixel art but are not yet on a real pixel grid.",
    ),
    "snap": (
        "pw snap {id}",
        "Finds the pixel grid the painter used and shrinks the image to true pixels.",
    ),
    "quantize": (
        "pw quantize {id}",
        "Maps every pixel to the palette, so colors stay few and consistent.",
    ),
    "clean": (
        "pw clean {id}",
        "Removes stray single pixels and anti-aliasing noise.",
    ),
    "check": (
        "pw check {id}",
        "Runs the automatic checks (palette, orphans, banding, contrast...) "
        "and marks where problems are.",
    ),
    "review-checks": (
        "pw issue {id} list",
        "Some checks flagged problems. Look at them with `pw check`, "
        "mark what matters as issues, then fix them.",
    ),
    "critique": (
        "pw critique {id} write --file critique.md",
        "Claude reviews the version against the style guide and the references, "
        "region by region, and records issues.",
    ),
    "fix": (
        "pw issue {id} list",
        "Open issues remain. Fix each one: `pw regen-region` repaints a region, "
        "`pw quantize/clean --mask` redo a step inside it, or retouch it in Aseprite.",
    ),
    "approve": (
        "pw approve {id} {version}",
        "Checks pass and no issue is open. If it looks right to you, approve it.",
    ),
    "export": (
        "pw export {id}",
        "Approved. Export writes the final file where the game expects it.",
    ),
    "done": (
        "pw new <next-asset> --kind <kind>",
        "This asset is exported. Start the next one.",
    ),
}

PIPELINE = ("generate", "snap", "quantize", "clean")


@dataclass(frozen=True)
class NextStep:
    step: str
    command: str
    why: str
    version: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _make(step: str, asset: Asset, version: str | None) -> NextStep:
    cmd, why = STEPS[step]
    return NextStep(step, cmd.format(id=asset.id, version=version or "<version>"), why, version)


def next_step(asset: Asset) -> NextStep:
    version = asset.latest()
    if version is None:
        has_sketch = any((asset.path / "inputs").glob("sketch.*"))
        return _make("generate" if has_sketch else "attach", asset, None)
    stage = asset.stage(version)
    if stage == "final":
        return _make("done", asset, version)
    if stage == "approved":
        return _make("export", asset, version)
    step = str(asset.meta(version)["step"])
    if step in PIPELINE[:-1]:
        return _make(PIPELINE[PIPELINE.index(step) + 1], asset, version)
    report = asset.versions_dir / version / "report.json"
    if not report.is_file():
        return _make("check", asset, version)
    if any(r["status"] == "fail" for r in read_report(report)):
        return _make("review-checks", asset, version)
    if any(i["status"] == "open" for i in asset.issues()):
        return _make("fix", asset, version)
    if not (asset.versions_dir / version / "critique.md").is_file():
        return _make("critique", asset, version)
    return _make("approve", asset, version)
