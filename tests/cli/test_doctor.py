"""`pw doctor`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pixelwright.cli import main


def test_doctor_reports_missing_key_with_env_var_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from pixelwright.core.providers import registry
    from pixelwright.core.providers.replay import ReplayProvider

    class Paid(ReplayProvider):
        needs_key = True

    monkeypatch.setitem(registry._FACTORIES, "paidtest", Paid)
    monkeypatch.delenv("PW_PAIDTEST_KEY", raising=False)
    ws = tmp_path / "ws"
    main(["init", str(ws)])
    capsys.readouterr()
    assert main(["doctor", "--offline", "--workspace", str(ws), "--json"]) == 0
    rows = {r["check"]: r for r in json.loads(capsys.readouterr().out)["data"]["rows"]}
    assert not rows["paidtest"]["ok"] and "PW_PAIDTEST_KEY" in rows["paidtest"]["fix"]
    assert rows["budget"]["ok"] and rows["python"]["ok"] and "comfyui" not in rows
    monkeypatch.setenv("PW_PAIDTEST_KEY", "x")
    main(["doctor", "--offline", "--workspace", str(ws)])
    out = capsys.readouterr().out
    assert "ok  paidtest" in out and "{" not in out


def test_doctor_comfyui_down_says_how_to_fix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws = tmp_path / "ws"
    main(["init", str(ws)])
    (ws / "pixelwright.toml").write_text(
        (ws / "pixelwright.toml").read_text()
        + '\n[providers.comfyui]\nbase_url = "http://127.0.0.1:9"\n'
    )
    capsys.readouterr()
    main(["doctor", "--workspace", str(ws), "--json"])
    rows = {r["check"]: r for r in json.loads(capsys.readouterr().out)["data"]["rows"]}
    assert not rows["comfyui"]["ok"] and "ComfyUI" in rows["comfyui"]["fix"]
