"""`pw generate` from the command line."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pixelwright.asset import Asset
from pixelwright.cli import main
from pixelwright.project import load_project


def test_dry_run_needs_no_api_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PW_PIXELLAB_KEY", raising=False)
    art = tmp_path / "art"
    assert main(["init", str(art)]) == 0
    Asset.create(load_project(art), "sprites/hero")
    capsys.readouterr()
    argv = [
        "generate",
        "sprites/hero",
        "--provider",
        "pixellab",
        "--prompt",
        "a knight",
        "--size",
        "64x64",
    ]
    code = main([*argv, "--dry-run", "--workspace", str(art), "--json"])
    env = json.loads(capsys.readouterr().out)
    assert code == 0, env
    assert env["data"]["request_hash"] and env["data"]["estimate_usd"] > 0
    assert not (art / ".pixelwright" / "secrets.toml").exists()
