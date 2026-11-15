import json
import socket
import time
from pathlib import Path

import pytest

from pixelwright.cli import main
from pixelwright.workspace import Workspace


def test_tour_runs_whole_loop_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_network(*args: object, **kwargs: object) -> None:
        raise OSError("network blocked in this test")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    started = time.perf_counter()
    code = main(["tour", "--path", str(tmp_path / "tour"), "--no-view", "--json"])
    seconds = time.perf_counter() - started
    out = capsys.readouterr()
    assert code == 0 and seconds <= 60
    env = json.loads(out.out)
    assert env["ok"] and env["stage"] == "final"
    asset = Workspace.open(tmp_path / "tour").asset("hillside")
    approved = [v for v in asset.versions() if asset.stage(v) in ("approved", "final")]
    assert approved == [env["version"]]
    assert (tmp_path / "tour" / env["outputs"][0]).is_file()
    for word in ("what happened:", "why:", "look at:"):
        assert out.err.count(word) == 8
