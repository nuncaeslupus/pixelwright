"""`pw bench run`: estimate first, spend only with --yes, resumable."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

import pytest

from pixelwright.cli import main
from pixelwright.fixtures import tour
from pixelwright.io.png import encode_png
from pixelwright.workspace import Workspace

MATRIX = """schema: pixelwright/bench-matrix@1
name: try
providers: [{providers}]
chains:
  full: [snap, quantize, clean]
  light: [snap]
samples: 2
briefs:
  - id: dusk
    prompt: a house on a hill at dusk
"""


def _pw(ws: Path, capsys: pytest.CaptureFixture[str], *args: str) -> dict[str, Any]:
    code = main([*args, "--workspace", str(ws), "--json"])
    out: dict[str, Any] = json.loads(capsys.readouterr().out)
    out["exit"] = code
    return out


@pytest.fixture
def ws(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    root = tmp_path / "ws"
    _pw(root, capsys, "init", "--legacy")
    (root / "replay").mkdir()
    (root / "replay" / "a.png").write_bytes(encode_png(tour.painted()))
    return root


def _matrix(tmp_path: Path, providers: str) -> str:
    path = tmp_path / "matrix.yaml"
    path.write_text(MATRIX.format(providers=providers), encoding="utf-8")
    return str(path)


def test_bench_run_refuses_without_yes_and_shows_estimate(
    ws: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("bench sent a request before --yes")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    matrix = _matrix(tmp_path, "replay, gemini")
    code = main(["bench", "run", "--matrix", matrix, "--workspace", str(ws)])
    text = capsys.readouterr().out
    assert code == 0 and "Nothing sent" in text and "total" in text  # estimate_shown_before_send
    out = _pw(ws, capsys, "bench", "run", "--matrix", matrix)
    rows = {r["provider"]: r for r in out["data"]["rows"]}
    assert out["data"]["sent"] == 0 and rows["gemini"]["usd"] == pytest.approx(0.078)
    assert rows["gemini"]["problem"] and not rows["replay"]["problem"]
    assert Workspace.open(ws).assets() == [] and not (ws / "cost.jsonl").exists()
    refused = _pw(ws, capsys, "bench", "run", "--matrix", matrix, "--yes")
    assert refused["exit"] != 0 and refused["error"]["code"] == "not_ready"


def test_bench_run_scores_every_sample_and_chain_and_resumes(
    ws: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    matrix = _matrix(tmp_path, "replay")
    out = _pw(ws, capsys, "bench", "run", "--matrix", matrix, "--yes")
    assert out["exit"] == 0, out
    scores = json.loads((ws / "benchmarks" / "try" / "scores.json").read_text())
    assert len(scores) == 4  # 1 brief x 1 provider x 2 samples x 2 chains
    assert {s["chain"] for s in scores} == {"full", "light"} and all("checks" in s for s in scores)
    again = _pw(ws, capsys, "bench", "run", "--matrix", matrix, "--yes")
    assert again["exit"] == 0 and again["data"]["sent"] == 4


def test_shipped_matrix_loads() -> None:
    from pixelwright.bench.matrix import load_matrix

    m = load_matrix(Path(__file__).parents[2] / "benchmarks" / "matrix.yaml")
    assert len(m.briefs) == 3 and len(m.chains) == 2 and m.samples == 3 and m.max_usd == 20
