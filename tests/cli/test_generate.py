"""`pw generate` with the offline replay provider."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from pixelwright.cli import main
from pixelwright.fixtures import tour
from pixelwright.io.png import encode_png


def _pw(ws: Path, capsys: pytest.CaptureFixture[str], *args: str) -> dict[str, Any]:
    code = main([*args, "--workspace", str(ws), "--json"])
    out: dict[str, Any] = json.loads(capsys.readouterr().out)
    out["exit"] = code
    return out


@pytest.fixture
def ws(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    root = tmp_path / "ws"
    assert _pw(root, capsys, "init")["exit"] == 0
    (root / "replay").mkdir()
    (root / "replay" / "a.png").write_bytes(encode_png(tour.painted()))
    (root / "replay" / "b.png").write_bytes(encode_png(tour.sketch()))
    _pw(root, capsys, "new", "hill", "--kind", "background", "--canvas", "160x90")
    sketch = tmp_path / "sketch.png"
    sketch.write_bytes(encode_png(tour.sketch()))
    _pw(root, capsys, "attach", "hill", str(sketch), "--as", "sketch")
    return root


def test_generate_n2_writes_two_versions_with_provider_meta(
    ws: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _pw(
        ws,
        capsys,
        "generate",
        "hill",
        "--provider",
        "replay",
        "--n",
        "2",
        "--prompt",
        "house on a hill at dusk",
        "--seed",
        "3",
    )
    assert out["exit"] == 0, out
    assert out["data"]["versions"] == ["v0001", "v0002"] and out["data"]["mode"] == "img2img"
    for v in out["data"]["versions"]:
        meta = yaml.safe_load((ws / "assets/hill/versions" / v / "meta.yaml").read_text())
        assert meta["provider"] == "replay" and meta["seed"] == 3 and meta["cost_usd"] == 0.0
        assert meta["request_hash"] == out["data"]["request_hash"]
        assert meta["step"] == "generate" and "init" in meta["inputs"]
    rows = (ws / "cost.jsonl").read_text().splitlines()
    assert len(rows) == 1 and json.loads(rows[0])["versions"] == ["v0001", "v0002"]


def test_generate_same_request_twice_is_cache_hit_with_same_bytes(
    ws: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ("generate", "hill", "--provider", "replay", "--prompt", "x", "--seed", "1")
    first = _pw(ws, capsys, *args)
    second = _pw(ws, capsys, *args)
    assert not first["data"]["cache_hit"] and second["data"]["cache_hit"]
    a = (ws / first["outputs"][0]).read_bytes()
    assert a == (ws / second["outputs"][0]).read_bytes()


def test_generate_dry_run_sends_nothing(ws: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = _pw(ws, capsys, "generate", "hill", "--provider", "replay", "--prompt", "x", "--dry-run")
    assert out["data"]["estimate_usd"] == 0.0 and out["data"]["size"] == [640, 360]
    assert not (ws / "assets/hill/versions/v0001").exists()


def test_generate_experiment_stage_and_txt2img(
    ws: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _pw(
        ws,
        capsys,
        "generate",
        "hill",
        "--provider",
        "replay",
        "--prompt",
        "x",
        "--mode",
        "txt2img",
        "--experiment",
    )
    assert out["stage"] == "experiment" and out["data"]["mode"] == "txt2img"


def test_generate_paid_provider_without_key_names_env_var(
    ws: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from pixelwright.core.providers import registry
    from pixelwright.core.providers.replay import ReplayProvider

    class Paid(ReplayProvider):
        needs_key = True

        def __init__(self, api_key: str, **kw: object) -> None:
            super().__init__(".")

    monkeypatch.setitem(registry._FACTORIES, "paidtest", Paid)
    monkeypatch.delenv("PW_PAIDTEST_KEY", raising=False)
    out = _pw(ws, capsys, "generate", "hill", "--provider", "paidtest", "--prompt", "x")
    assert out["exit"] == 2 and "PW_PAIDTEST_KEY" in out["error"]["message"]


def test_generate_uses_style_preamble(ws: Path, capsys: pytest.CaptureFixture[str]) -> None:
    style = ws / "style" / "style.yaml"
    data = yaml.safe_load(style.read_text())
    data["presets"] = {"replay": {"preamble": "pixel art, VGA adventure,"}}
    style.write_text(yaml.safe_dump(data))
    out = _pw(
        ws, capsys, "generate", "hill", "--provider", "replay", "--prompt", "a hill", "--dry-run"
    )
    assert out["data"]["prompt"] == "pixel art, VGA adventure, a hill"
