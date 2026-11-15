"""`matrix.yaml`: what a benchmark runs (providers x chains x briefs x samples)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pixelwright.workspace.files import read_yaml

SCHEMA = "pixelwright/bench-matrix@1"
STEPS = ("snap", "quantize", "clean")
DEFAULT_CAP_USD = 20.0  # D-16: the first benchmark costs at most 20 USD


@dataclass(frozen=True)
class Brief:
    id: str
    prompt: str
    kind: str = "background"
    canvas: str = "160x90"
    sketch: Path | None = None
    palette: str | None = None  # a palette under style/, as `pw new --palette` takes it


@dataclass(frozen=True)
class Matrix:
    name: str
    providers: tuple[str, ...]
    chains: dict[str, tuple[str, ...]]
    briefs: tuple[Brief, ...]
    samples: int = 3
    max_usd: float = DEFAULT_CAP_USD
    seed: int = 1
    colors: int = 16  # palette size discovered by quantize when a brief has no palette
    extra: dict[str, Any] = field(default_factory=dict)


def load_matrix(path: Path) -> Matrix:
    data = read_yaml(path)
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError(f"{path}: not a {SCHEMA} file")
    chains = {str(k): tuple(v) for k, v in (data.get("chains") or {"full": STEPS}).items()}
    for name, steps in chains.items():
        bad = [s for s in steps if s not in STEPS]
        if bad:
            raise ValueError(f"chain {name}: unknown steps {bad}; use {STEPS}")
    briefs = []
    for b in data.get("briefs") or []:
        sketch = b.get("sketch")
        briefs.append(
            Brief(
                id=str(b["id"]),
                prompt=str(b["prompt"]),
                kind=str(b.get("kind", "background")),
                canvas=str(b.get("canvas", "160x90")),
                sketch=(path.parent / sketch) if sketch else None,
                palette=b.get("palette"),
            )
        )
    providers = tuple(str(p) for p in data.get("providers") or [])
    if not providers or not briefs:
        raise ValueError(f"{path}: needs at least one provider and one brief")
    samples = int(data.get("samples", 3))
    if not 1 <= samples <= 4:
        raise ValueError("samples must be between 1 and 4")
    return Matrix(
        name=str(data.get("name", path.stem)),
        providers=providers,
        chains=chains,
        briefs=tuple(briefs),
        samples=samples,
        max_usd=float(data.get("max_usd", DEFAULT_CAP_USD)),
        seed=int(data.get("seed", 1)),
        colors=int(data.get("colors", 16)),
    )
