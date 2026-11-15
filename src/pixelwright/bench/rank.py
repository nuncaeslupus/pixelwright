"""Pairwise votes on benchmark results, and a Bradley-Terry ranking of the systems.

An item is one scored result (`asset/version`); its system is `provider + chain`. Pairs are
drawn only within one brief, between different systems. Readers are `claude` (votes through
MCP or the CLI, may see file names) and `human` (votes on the blind page, sees only opaque
tokens). Votes are appended to `<reader>_pairs.jsonl` beside `scores.json`.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

READERS = ("claude", "human")
WINNERS = ("a", "b", "tie")


def token(name: str, key: str) -> str:
    return hashlib.sha256(f"{name}:{key}".encode()).hexdigest()[:12]


def items(out: Path) -> list[dict[str, Any]]:
    scores = json.loads((out / "scores.json").read_text(encoding="utf-8"))
    rows = []
    for s in scores:
        key = f"{s['asset']}/{s['version']}"
        system = f"{s['provider']} + {s['chain']}"
        rows.append({**s, "key": key, "system": system, "token": token(out.name, key)})
    return rows


def votes(out: Path, reader: str | None = None) -> list[dict[str, Any]]:
    found = []
    for r in READERS if reader is None else (reader,):
        path = out / f"{r}_pairs.jsonl"
        if path.is_file():
            lines = path.read_text(encoding="utf-8").splitlines()
            found += [json.loads(line) for line in lines if line.strip()]
    return found


def all_pairs(rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    by_brief: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_brief[r["brief"]].append(r)
    pairs = []
    for group in by_brief.values():
        for a, b in itertools.combinations(group, 2):
            if a["system"] != b["system"]:
                pairs.append((a, b))
    # a stable shuffle, so sides and order do not follow the run order
    pairs.sort(key=lambda p: hashlib.sha256((p[0]["token"] + p[1]["token"]).encode()).digest())
    return [(b, a) if int(a["token"], 16) % 2 else (a, b) for a, b in pairs]


def next_pair(out: Path, reader: str) -> dict[str, Any] | None:
    rows = items(out)
    seen = {frozenset((v["a"], v["b"])) for v in votes(out, reader)}
    todo = [p for p in all_pairs(rows) if frozenset((p[0]["token"], p[1]["token"])) not in seen]
    if not todo:
        return None
    a, b = todo[0]
    pair: dict[str, Any] = {"a": a["token"], "b": b["token"], "left": len(todo)}
    if reader == "claude":  # Claude needs the files; the blind page never gets them
        pair["a_file"] = f"assets/{a['asset']}/versions/{a['version']}/image.png"
        pair["b_file"] = f"assets/{b['asset']}/versions/{b['version']}/image.png"
        pair["brief"] = a["brief"]
    return pair


def record(out: Path, reader: str, a: str, b: str, winner: str, note: str = "") -> dict[str, Any]:
    if reader not in READERS:
        raise ValueError(f"reader must be one of {READERS}")
    if winner not in WINNERS:
        raise ValueError(f"winner must be one of {WINNERS}")
    known = {r["token"] for r in items(out)}
    if a not in known or b not in known or a == b:
        raise ValueError("a and b must be two different items of this benchmark")
    vote = {"a": a, "b": b, "winner": winner, "note": note}
    with (out / f"{reader}_pairs.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(vote) + "\n")
    return vote


def bradley_terry(
    systems: list[str], games: list[tuple[str, str, float]], iterations: int = 200
) -> dict[str, float]:
    """Strengths (summing to 1) from games `(i, j, score_i)`, score 1 win, 0.5 tie, 0 loss.

    Hunter's MM update with a small prior (one tie against an average player), so a system
    that never wins keeps a finite, small strength.
    """
    p = dict.fromkeys(systems, 1.0)
    for _ in range(iterations):
        new = {}
        for i in systems:
            wins, denom = 0.5, 1.0 / (p[i] + 1.0)  # the prior
            for a, b, s in games:
                if i in (a, b):
                    j = b if i == a else a
                    wins += s if i == a else 1.0 - s
                    denom += 1.0 / (p[i] + p[j])
            new[i] = wins / denom
        total = sum(new.values())
        p = {k: v * len(systems) / total for k, v in new.items()}
    total = sum(p.values())
    return {k: v / total for k, v in p.items()}


def ranking(out: Path, reader: str | None = None) -> list[dict[str, Any]]:
    """Systems by strength, with vote counts and the mean detector failures."""
    rows = items(out)
    system_of = {r["token"]: r["system"] for r in rows}
    games = []
    for v in votes(out, reader):
        score = {"a": 1.0, "b": 0.0, "tie": 0.5}[v["winner"]]
        games.append((system_of[v["a"]], system_of[v["b"]], score))
    systems = sorted({r["system"] for r in rows})
    strength = bradley_terry(systems, games)
    fails: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        fails[r["system"]].append(int(r["fails"]))
    table = [
        {
            "system": s,
            "provider": s.split(" + ")[0],
            "chain": s.split(" + ")[1],
            "strength": round(strength[s], 4),
            "games": sum(s in (a, b) for a, b, _ in games),
            "mean_fails": round(sum(fails[s]) / len(fails[s]), 2),
        }
        for s in systems
    ]
    return sorted(table, key=lambda r: (-r["strength"], r["mean_fails"], r["system"]))
