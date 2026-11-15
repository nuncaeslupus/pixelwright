"""Provider response cache in the workspace `cache/`, keyed by request hash."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from pixelwright.core.providers.base import Cost, GenResult

SECRET_KEYS = frozenset({"authorization", "api_key", "apikey", "key", "x-api-key", "token"})


def strip_secrets(value: Any) -> Any:
    """Drop any dict entry whose key names a credential, recursively."""
    if isinstance(value, dict):
        return {k: strip_secrets(v) for k, v in value.items() if k.lower() not in SECRET_KEYS}
    if isinstance(value, list):
        return [strip_secrets(v) for v in value]
    return value


class Cache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _dir(self, key: str) -> Path:
        return self.root / key[:2] / key

    def get(self, key: str) -> GenResult | None:
        d = self._dir(key)
        meta_path = d / "response.json"
        if not meta_path.is_file():
            return None
        meta = json.loads(meta_path.read_text())
        images = [(d / f"out_{i}.png").read_bytes() for i in range(meta["n_images"])]
        return GenResult(
            images=images,
            raw=meta["raw"],
            cost=Cost(0.0, len(images)),
            model=meta.get("model", ""),
            seed=meta.get("seed"),
            cache_hit=True,
            request_hash=key,
        )

    def put(self, key: str, request: dict[str, Any], result: GenResult) -> None:
        """Write to a temp dir, then rename, so a crash never leaves a half entry."""
        final = self._dir(key)
        if final.exists():
            return
        final.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(dir=final.parent, prefix=".tmp-"))
        try:
            (tmp / "request.json").write_text(json.dumps(request, sort_keys=True, indent=1))
            for i, img in enumerate(result.images):
                (tmp / f"out_{i}.png").write_bytes(img)
            meta = {
                "n_images": len(result.images),
                "raw": strip_secrets(result.raw),
                "model": result.model,
                "seed": result.seed,
                "cost_usd": result.cost.usd,
            }
            (tmp / "response.json").write_text(json.dumps(meta, sort_keys=True, indent=1))
            os.replace(tmp, final)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
