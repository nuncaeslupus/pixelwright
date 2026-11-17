"""Bradley-Terry ranking and the pairwise vote commands."""

from __future__ import annotations

import itertools
import json
import random
from pathlib import Path
from typing import Any

import pytest

from pixelwright.bench.rank import bradley_terry, items
from pixelwright.cli import main
from pixelwright.fixtures.bench import bench_workspace
from pixelwright.project import load_project


def test_bradley_terry_recovers_known_order() -> None:
    true = {"a": 8.0, "b": 4.0, "c": 2.0, "d": 1.0}
    rng = random.Random(3)
    games = []
    for i, j in itertools.combinations(true, 2):
        for _ in range(60):
            games.append((i, j, 1.0 if rng.random() < true[i] / (true[i] + true[j]) else 0.0))
    got = bradley_terry(list(true), games)
    assert sorted(got, key=got.__getitem__, reverse=True) == ["a", "b", "c", "d"]
    assert sum(got.values()) == pytest.approx(1.0)


def _pw(ws: Path, capsys: pytest.CaptureFixture[str], *args: str) -> dict[str, Any]:
    code = main([*args, "--workspace", str(ws), "--json"])
    out: dict[str, Any] = json.loads(capsys.readouterr().out)
    out["exit"] = code
    return out


def test_votes_rank_report_and_apply(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ws = tmp_path / "ws"
    out = bench_workspace(ws)
    capsys.readouterr()
    pair = _pw(ws, capsys, "bench", "pair")["data"]["pair"]
    assert pair["a_file"].startswith("assets/bench/") and pair["left"] == 8  # 2 briefs x 4
    voted = 0
    chain = {r["token"]: r["chain"] for r in items(out)}
    while pair:  # always prefer the full chain
        winner = "a" if chain[pair["a"]] == "full" else "b"
        res = _pw(
            ws, capsys, "bench", "vote", "--a", pair["a"], "--b", pair["b"], "--winner", winner
        )
        pair, voted = res["data"]["next"], voted + 1
    assert voted == 8
    ranked = _pw(ws, capsys, "bench", "rank")["data"]["ranking"]
    assert ranked[0]["system"] == "replay + full" and ranked[0]["games"] == 8
    report = _pw(ws, capsys, "bench", "report")
    assert "Bradley-Terry" in (ws / report["data"]["report"]).read_text()
    applied = _pw(ws, capsys, "bench", "apply")
    assert applied["data"]["defaults"] == {"background": "replay"}
    assert load_project(ws).extra["defaults"]["background"] == "replay"
    bad = _pw(ws, capsys, "bench", "vote", "--a", "nope", "--b", "nope2", "--winner", "a")
    assert bad["exit"] != 0
