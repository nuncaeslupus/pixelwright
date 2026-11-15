"""Provider contract (spec §5): requests, results, capabilities, errors, request hashing."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

Mode = Literal["txt2img", "img2img", "edit", "inpaint"]
MODES: tuple[str, ...] = ("txt2img", "img2img", "edit", "inpaint")

# Exit codes shared with the CLI envelope (spec §5).
EXIT_USAGE = 2
EXIT_PROVIDER = 5
EXIT_BUDGET = 6


class ProviderError(Exception):
    """A provider failure with a stable `code`; the CLI turns it into the envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        exit_code: int = EXIT_PROVIDER,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.details = details or {}


@dataclass(frozen=True)
class Capabilities:
    modes: tuple[str, ...] = ("txt2img",)
    n_references: int = 0
    style_refs: bool = False
    palette_input: bool = False
    max_size: tuple[int, int] = (1024, 1024)
    max_n: int = 1
    price_per_image: float = 0.0  # USD
    watermark: bool = False
    licence_note: str = ""


@dataclass(frozen=True)
class GenRequest:
    mode: str
    prompt: str
    size: tuple[int, int]
    negative: str = ""
    init_image: Path | None = None
    mask: Path | None = None
    references: tuple[Path, ...] = ()
    palette: tuple[str, ...] | None = None
    seed: int | None = None
    n: int = 1
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ProviderError("bad_mode", f"mode must be one of {MODES}", exit_code=EXIT_USAGE)
        if not 1 <= self.n <= 4:
            raise ProviderError("bad_n", "n must be between 1 and 4", exit_code=EXIT_USAGE)
        if self.mode in ("img2img", "edit", "inpaint") and self.init_image is None:
            raise ProviderError(
                "missing_init_image", f"mode {self.mode} needs an init image", exit_code=EXIT_USAGE
            )
        if self.mode == "inpaint" and self.mask is None:
            raise ProviderError("missing_mask", "mode inpaint needs a mask", exit_code=EXIT_USAGE)

    def canonical(self) -> dict[str, Any]:
        """JSON-ready form with every image path replaced by the SHA-256 of its bytes."""
        data = asdict(self)
        data["size"] = list(self.size)
        data["init_image"] = _file_hash(self.init_image)
        data["mask"] = _file_hash(self.mask)
        data["references"] = [_file_hash(p) for p in self.references]
        data["palette"] = list(self.palette) if self.palette is not None else None
        return data


@dataclass(frozen=True)
class Cost:
    usd: float
    images: int = 1


@dataclass
class GenResult:
    images: list[bytes]  # PNG bytes, one per candidate
    raw: dict[str, Any]  # provider response, secrets stripped
    cost: Cost
    model: str = ""
    seed: int | None = None
    cache_hit: bool = False
    request_hash: str = ""


class Provider(Protocol):
    name: str
    capabilities: Capabilities

    def estimate(self, req: GenRequest) -> Cost: ...

    def generate(self, req: GenRequest) -> GenResult: ...


def _file_hash(path: Path | None) -> str | None:
    if path is None:
        return None
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def request_hash(provider: str, req: GenRequest) -> str:
    """SHA-256 of canonical JSON (sorted keys, no spaces) of provider name and request."""
    body = {"provider": provider, "request": req.canonical()}
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def check_capability(provider: Provider, req: GenRequest) -> None:
    """Refuse a request the provider cannot serve, before anything is sent."""
    caps = provider.capabilities
    problems = []
    if req.mode not in caps.modes:
        problems.append(f"mode {req.mode}")
    if len(req.references) > caps.n_references:
        problems.append(f"{len(req.references)} references (max {caps.n_references})")
    if req.n > caps.max_n:
        problems.append(f"n={req.n} (max {caps.max_n})")
    w, h = req.size
    if w > caps.max_size[0] or h > caps.max_size[1]:
        problems.append(f"size {w}x{h} (max {caps.max_size[0]}x{caps.max_size[1]})")
    if problems:
        raise ProviderError(
            "capability_missing",
            f"provider {provider.name} does not support: {', '.join(problems)}",
            exit_code=EXIT_USAGE,
            details={"provider": provider.name, "unsupported": problems},
        )
