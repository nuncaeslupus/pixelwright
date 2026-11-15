"""Keys, the cost ledger (`cost.jsonl`) and the monthly budget guard (spec M3, D-M3-2/3)."""

from __future__ import annotations

import json
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pixelwright.core.providers.base import (
    EXIT_BUDGET,
    EXIT_USAGE,
    GenRequest,
    GenResult,
    Provider,
    ProviderError,
)
from pixelwright.core.providers.run import Guard
from pixelwright.workspace.config import WorkspaceConfig
from pixelwright.workspace.files import append_jsonl

SECRETS_PATH = ".pixelwright/secrets.toml"
LEDGER_NAME = "cost.jsonl"
DEFAULT_MONTHLY_USD = 5.0


def env_var(provider: str) -> str:
    return "PW_" + provider.upper().replace("-", "_") + "_KEY"


def api_key(root: Path, provider: str, env: Mapping[str, str] | None = None) -> str:
    """The provider's key: env var `PW_<NAME>_KEY` first, then `.pixelwright/secrets.toml`."""
    env = os.environ if env is None else env
    if env.get(env_var(provider)):
        return env[env_var(provider)]
    path = root / SECRETS_PATH
    if path.is_file():
        with path.open("rb") as fh:
            keys = tomllib.load(fh).get("keys", {})
        if isinstance(keys.get(provider), str) and keys[provider]:
            return str(keys[provider])
    raise ProviderError(
        "missing_key",
        f"no API key for {provider}: set {env_var(provider)} or add "
        f'`{provider} = "..."` under [keys] in {SECRETS_PATH}',
        exit_code=EXIT_USAGE,
        details={"provider": provider, "env_var": env_var(provider), "file": SECRETS_PATH},
    )


def monthly_limit(config: WorkspaceConfig) -> float:
    budget = config.extra.get("budget", {})
    return float(budget.get("monthly_usd", DEFAULT_MONTHLY_USD))


def month_of(stamp: str) -> str:
    return stamp[:7]


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Ledger:
    root: Path

    @property
    def path(self) -> Path:
        return self.root / LEDGER_NAME

    def rows(self, month: str | None = None) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        rows = [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]
        return [r for r in rows if month is None or month_of(r["time"]) == month]

    def spent(self, month: str) -> float:
        return round(sum(float(r["cost_usd"]) for r in self.rows(month)), 6)

    def record(
        self,
        provider: str,
        result: GenResult,
        *,
        asset: str | None = None,
        versions: list[str] | None = None,
        now: str | None = None,
    ) -> dict[str, Any]:
        row = {
            "time": now or _now(),
            "provider": provider,
            "model": result.model,
            "request_hash": result.request_hash,
            "n": len(result.images),
            "cost_usd": 0.0 if result.cache_hit else result.cost.usd,
            "cache_hit": result.cache_hit,
            "asset": asset,
            "versions": versions or [],
        }
        append_jsonl(self.path, row)
        return row


def budget_guard(root: Path, config: WorkspaceConfig, now: str | None = None) -> Guard:
    """A guard for `providers.run`: refuse a call that would pass the monthly limit."""
    limit = monthly_limit(config)
    month = month_of(now or _now())

    def guard(provider: Provider, req: GenRequest, estimate_usd: float) -> None:
        spent = Ledger(root).spent(month)
        if spent + estimate_usd > limit + 1e-9:
            raise ProviderError(
                "budget_exceeded",
                f"{provider.name}: this call (~{estimate_usd:.2f} USD) would pass the monthly "
                f"budget ({spent:.2f} of {limit:.2f} USD spent in {month}); raise "
                "[budget] monthly_usd in pixelwright.toml to allow it",
                exit_code=EXIT_BUDGET,
                details={"spent_usd": spent, "limit_usd": limit, "estimate_usd": estimate_usd},
            )

    return guard
