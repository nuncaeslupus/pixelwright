"""`pw tour`: the whole loop on a bundled sample, offline, in plain words.

The sample is drawn by code (`fixtures/tour.py`); the painter is the offline `replay`
provider, so the tour needs no GPU, no key and no network. Each step runs the same command
a user would type and prints what happened, why, and what to look at.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

from pixelwright.cli.registry import REGISTRY, Outcome, Param, command
from pixelwright.fixtures import tour as sample
from pixelwright.io.palette_io import write_palette
from pixelwright.io.png import encode_png
from pixelwright.workspace import Workspace
from pixelwright.workspace.next_step import next_step

ASSET = "hillside"
PROMPT = "a small house on a hillside at dusk, warm lit window, pixel art"

CRITIQUE = """---
schema: pixelwright/critique@1
version: {version}
verdict: fine
---
## Focal area
rule: R-VAL-1

The lit window is the brightest value and sits on the house, so the eye lands there first.
"""


def _say(n: int, title: str, did: str, why: str, look: str) -> None:
    print(
        f"\n[{n}] {title}\n  what happened: {did}\n  why: {why}\n  look at: {look}", file=sys.stderr
    )


@command(
    "tour",
    "run the whole loop on a sample, offline, explaining each step (start here)",
    Param("path", help="keep the tour workspace in this folder (default: a temporary one)"),
    Param("no_view", "bool", help="do not open the viewer at the end"),
    needs_workspace=False,
)
def cmd_tour(root: Path, a: dict[str, Any]) -> Outcome:
    path = Path(a["path"]) if a["path"] else Path(tempfile.mkdtemp(prefix="pw-tour-"))
    ws_root = path.resolve()

    def pw(name: str, **args: Any) -> Outcome:
        cmd = REGISTRY[name]
        full = {p.name: args.get(p.name, [] if p.kind == "list" else p.default) for p in cmd.params}
        return cmd.run(ws_root, full)

    def hint() -> str:
        step = next_step(Workspace.open(ws_root).asset(ASSET))
        return f"`pw next {ASSET}` now says: {step.step} ({step.command})"

    pw("init", path=str(ws_root), legacy=True, canvas=f"{sample.WIDTH}x{sample.HEIGHT}")
    files = ws_root / "tour-files"
    files.mkdir()
    write_palette(files / "dusk.gpl", sample.palette())
    (files / "sketch.png").write_bytes(encode_png(sample.sketch()))
    replay = ws_root / "replay"
    replay.mkdir()
    (replay / "painted.png").write_bytes(encode_png(sample.painted()))
    _say(
        1,
        "A workspace",
        f"created {ws_root} with pixelwright.toml, a style guide and an assets folder.",
        "every asset, version and decision lives in plain files here, so nothing is hidden.",
        "pixelwright.toml (canvas 160x90) and style/.",
    )

    pw("palette", action="import", file=str(files / "dusk.gpl"))
    pw("new", asset=ASSET, kind="background", palette="palettes/dusk.gpl")
    pw("attach", asset=ASSET, file=str(files / "sketch.png"), **{"as": "sketch"})
    _say(
        2,
        "An asset and its sketch",
        f"new asset '{ASSET}' (a 160x90 background) with a 12-colour dusk palette and a sketch.",
        "the sketch fixes the composition; the palette fixes the colours the game allows.",
        f"assets/{ASSET}/inputs/sketch.png. {hint()}",
    )

    gen = pw("generate", asset=ASSET, provider="replay", prompt=PROMPT, n=1)
    _say(
        3,
        "The painter",
        f"`pw generate` asked an image model for a painting: {gen.version}. Here the model is "
        "`replay`, which answers from recorded images, so the tour is free and offline.",
        "image models paint well but their pixels are fake: soft edges, noise, an uneven grid.",
        f"the {gen.version} image is 640x360, four times too big, and blurry up close.",
    )

    snap = pw("snap", asset=ASSET)
    _say(
        4,
        "Snap to the real grid",
        f"found the painter's pixel size ({snap.data.get('scale')}x) and shrank to {snap.version}.",
        "one image pixel should be one game pixel.",
        f"{snap.version} is 160x90. {hint()}",
    )

    quant = pw("quantize", asset=ASSET)
    clean = pw("clean", asset=ASSET)
    _say(
        5,
        "Palette and clean-up",
        f"quantize mapped every pixel to the palette ({quant.version}); clean removed stray "
        f"pixels ({clean.version}).",
        "few, consistent colours and no noise are what make pixel art read as pixel art.",
        f"compare {snap.version} and {clean.version} in the viewer. {hint()}",
    )

    checked = pw("check", asset=ASSET)
    results = checked.data.get("results", [])
    failed = [r["check"] for r in results if r["status"] == "fail"]
    _say(
        6,
        "Automatic checks",
        f"ran {len(results)} checks; {len(failed)} flagged: {', '.join(failed) or 'none'}.",
        "rules a machine can measure (palette, orphan pixels, banding, contrast) are checked "
        "by code, so review time goes to what needs an eye.",
        f"the Checks panel in the viewer marks where each problem is. {hint()}",
    )

    crit = files / "critique.md"
    crit.write_text(CRITIQUE.format(version=clean.version), encoding="utf-8")
    pw("critique", asset=ASSET, action="write", file=str(crit))
    _say(
        7,
        "Critique",
        "stored a critique: a review against the style guide, one section per complaint.",
        "in real work Claude writes it after looking at the image; complaints become issues "
        "you fix with `pw regen-region`, a masked quantize or clean, or Aseprite.",
        f"assets/{ASSET}/versions/{clean.version}/critique.md. {hint()}",
    )

    pw("approve", asset=ASSET, version=clean.version, note="tour: looks right")
    exported = pw("export", asset=ASSET)
    _say(
        8,
        "Approve and export",
        f"approved {clean.version} and exported it to {exported.outputs[0]}.",
        "only an approved version can be exported; the decision is in the asset's history.",
        f"the exported file, and `pw history {ASSET}`.",
    )

    text = (
        f"\nTour done. Workspace: {ws_root}\n"
        f"See it: pw view --workspace {ws_root} --open {ASSET}\n"
        "Your own first asset: pw init <folder>, then pw new <id> --kind background, "
        "then follow `pw next <id>`."
    )
    data = {"root": str(ws_root), "approved": clean.version, "exported": exported.outputs}
    if not a["no_view"]:
        print(text, file=sys.stderr)
        pw("view", open=f"{ASSET}/{clean.version}")
    return Outcome(ASSET, clean.version, "final", list(exported.outputs), data, text=text)
