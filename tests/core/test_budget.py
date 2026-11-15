"""Budget guard, cost ledger, keys and `pw cost`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pixelwright.cli import main
from pixelwright.core import providers as pv
from pixelwright.workspace import Workspace, WorkspaceConfig
from pixelwright.workspace.budget import Ledger, api_key, budget_guard


class PaidProvider:
    name = "paid"
    capabilities = pv.Capabilities(max_n=4, price_per_image=1.5)

    def __init__(self) -> None:
        self.sent = 0

    def estimate(self, req: pv.GenRequest) -> pv.Cost:
        return pv.Cost(1.5 * req.n, req.n)

    def generate(self, req: pv.GenRequest) -> pv.GenResult:
        self.sent += 1
        return pv.GenResult([b"png"] * req.n, {}, self.estimate(req), "m")


def _ws(tmp_path: Path, limit: float | None = None) -> Workspace:
    config = WorkspaceConfig()
    if limit is not None:
        config.extra["budget"] = {"monthly_usd": limit}
    return Workspace.init(tmp_path / "ws", config)


def test_call_over_budget_is_refused_before_send(tmp_path: Path) -> None:
    ws = _ws(tmp_path, limit=4.0)
    prov, now = PaidProvider(), "2026-11-15T10:00:00Z"
    guard = budget_guard(ws.root, ws.config, now=now)
    res = pv.run(prov, pv.GenRequest("txt2img", "a", (8, 8), n=2), guard=guard)
    Ledger(ws.root).record("paid", res, now=now)
    with pytest.raises(pv.ProviderError) as e:
        pv.run(prov, pv.GenRequest("txt2img", "b", (8, 8), n=1), guard=guard)
    assert e.value.code == "budget_exceeded" and e.value.exit_code == 6
    assert prov.sent == 1
    assert e.value.details == {"spent_usd": 3.0, "limit_usd": 4.0, "estimate_usd": 1.5}


def test_default_budget_is_five_usd(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    guard = budget_guard(ws.root, ws.config, now="2026-11-15T10:00:00Z")
    with pytest.raises(pv.ProviderError, match=r"5\.00 USD"):
        pv.run(PaidProvider(), pv.GenRequest("txt2img", "a", (8, 8), n=4), guard=guard)


def test_ledger_counts_cache_hits_as_free_and_by_month(tmp_path: Path) -> None:
    led = Ledger(tmp_path)
    res = pv.GenResult([b"x"], {}, pv.Cost(0.5), "m")
    led.record("p", res, now="2026-10-31T23:00:00Z")
    led.record("p", res, now="2026-11-01T00:00:00Z")
    res.cache_hit = True
    led.record("p", res, now="2026-11-02T00:00:00Z")
    assert led.spent("2026-11") == 0.5 and led.spent("2026-10") == 0.5
    assert len(led.rows("2026-11")) == 2


def test_env_key_wins_over_secrets_file(tmp_path: Path) -> None:
    (tmp_path / ".pixelwright").mkdir()
    (tmp_path / ".pixelwright/secrets.toml").write_text('[keys]\nretro-diffusion = "file"\n')
    assert api_key(tmp_path, "retro-diffusion", env={}) == "file"
    env = {"PW_RETRO_DIFFUSION_KEY": "env"}
    assert api_key(tmp_path, "retro-diffusion", env=env) == "env"


def test_missing_key_names_env_var_and_file(tmp_path: Path) -> None:
    with pytest.raises(pv.ProviderError) as e:
        api_key(tmp_path, "gemini", env={})
    assert e.value.code == "missing_key" and "PW_GEMINI_KEY" in e.value.message
    assert ".pixelwright/secrets.toml" in e.value.message


def test_init_gitignores_secrets_file(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    assert "/.pixelwright/secrets.toml" in (ws.root / ".gitignore").read_text().splitlines()


def test_cost_command_groups_by_provider(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws = _ws(tmp_path)
    led = Ledger(ws.root)
    led.record("a", pv.GenResult([b"x"], {}, pv.Cost(0.25), "m"), now="2026-11-02T00:00:00Z")
    led.record("b", pv.GenResult([b"x"], {}, pv.Cost(0.5), "m"), now="2026-11-03T00:00:00Z")
    code = main(
        ["cost", "--workspace", str(ws.root), "--month", "2026-11", "--by", "provider", "--json"]
    )
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["data"]["spent_usd"] == 0.75 and out["data"]["limit_usd"] == 5.0
    assert out["data"]["rows"] == [
        {"provider": "a", "cost_usd": 0.25},
        {"provider": "b", "cost_usd": 0.5},
    ]
