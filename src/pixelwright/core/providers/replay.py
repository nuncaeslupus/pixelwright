"""`replay`: an offline provider that answers from a folder of images (tour, tests, demos).

An answer is looked up first by request hash (`<folder>/<hash>/out_<n>.png`, the cache
layout, so a recorded run replays exactly), then from the folder's top-level `*.png` files,
picked in order starting at a position derived from the request hash. Always free.
"""

from __future__ import annotations

from pathlib import Path

from pixelwright.core.providers.base import (
    MODES,
    Capabilities,
    Cost,
    GenRequest,
    GenResult,
    ProviderError,
    request_hash,
)
from pixelwright.core.providers.registry import register


class ReplayProvider:
    name = "replay"
    capabilities = Capabilities(
        modes=MODES,
        n_references=8,
        style_refs=True,
        palette_input=True,
        max_size=(4096, 4096),
        max_n=4,
        price_per_image=0.0,
        licence_note="replays the workspace's own images",
    )

    def __init__(self, folder: str | Path) -> None:
        self.folder = Path(folder)

    def estimate(self, req: GenRequest) -> Cost:
        return Cost(0.0, req.n)

    def generate(self, req: GenRequest) -> GenResult:
        key = request_hash(self.name, req)
        recorded = self.folder / key[:2] / key
        if recorded.is_dir():
            files = sorted(recorded.glob("out_*.png"))[: req.n]
        else:
            pool = sorted(self.folder.glob("*.png"))
            if not pool:
                raise ProviderError("provider_unavailable", f"replay: no images in {self.folder}")
            start = int(key[:8], 16) % len(pool)
            files = [pool[(start + i) % len(pool)] for i in range(req.n)]
        return GenResult(
            images=[f.read_bytes() for f in files],
            raw={"replay": [f.name for f in files]},
            cost=Cost(0.0, len(files)),
            model="replay",
            seed=req.seed,
        )


register("replay", ReplayProvider)
