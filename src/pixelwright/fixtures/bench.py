"""A finished offline benchmark for tests and demos (replay provider, tour sample)."""

from __future__ import annotations

from pathlib import Path

from pixelwright.cli import main
from pixelwright.fixtures import tour
from pixelwright.io.png import encode_png


def bench_workspace(root: Path) -> Path:
    """A workspace with one finished benchmark `try`: replay x 2 chains x 2 briefs x 2."""
    w = ["--workspace", str(root)]
    if not (root / "pixelwright.toml").is_file():
        assert main(["init", *w]) == 0
    (root / "replay").mkdir(exist_ok=True)
    (root / "replay" / "a.png").write_bytes(encode_png(tour.painted()))
    matrix = root / "matrix.yaml"
    matrix.write_text(
        "schema: pixelwright/bench-matrix@1\nname: try\nproviders: [replay]\n"
        "chains:\n  full: [snap, quantize, clean]\n  light: [snap]\nsamples: 2\n"
        "briefs:\n  - id: dusk\n    prompt: dusk\n  - id: noon\n    prompt: noon\n"
    )
    assert main(["bench", "run", "--matrix", str(matrix), "--yes", *w]) == 0
    return root / "benchmarks" / "try"
