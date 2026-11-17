import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from pixelwright.cli import main
from pixelwright.core.image import RGBImage
from pixelwright.io.png import write_png


def pw(capsys: pytest.CaptureFixture[str], *argv: str, code: int = 0) -> dict[str, Any]:
    got = main([*argv, "--json"])
    env: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert got == code, env
    return env


@pytest.fixture
def ws(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> list[str]:
    rgba = np.zeros((6, 8, 4), np.uint8)
    rgba[1:5, 2:6] = (200, 40, 40, 255)
    write_png(tmp_path / "hero.png", RGBImage(rgba))
    w = ["--workspace", str(tmp_path / "ws")]
    pw(capsys, "init", "--legacy", *w, "--canvas", "8x6")
    pw(capsys, "new", "hero", "--kind", "sprite", *w)
    pw(capsys, "attach", "hero", str(tmp_path / "hero.png"), *w)
    return w


def test_issue_add_list_resolve(ws: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    added = pw(capsys, "issue", "hero", "add", "--box", "1,1,2,2", "--rule", "R-PIX-3", *ws)
    issue = added["data"]["issue"]
    assert issue["id"] == "r-pix-3-1" and issue["version"] == "v0001"
    pw(capsys, "issue", "hero", "add", "--note", "too dark", "--author", "human", *ws)
    pw(capsys, "issue", "hero", "resolve", "--id", "r-pix-3-1", *ws)
    open_ = pw(capsys, "issue", "hero", "list", "--status", "open", *ws)["data"]["issues"]
    assert [i["id"] for i in open_] == ["issue-1"]
    bad = pw(capsys, "issue", "hero", "add", "--box", "1,2", *ws, code=3)
    assert bad["error"]["code"] == "invalid"


def test_inbox_since_lists_new_versions_and_decisions(
    ws: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    pw(capsys, "issue", "hero", "add", "--note", "claude was here", *ws)
    pw(capsys, "approve", "hero", "v0001", "--note", "ok", *ws)
    items = pw(capsys, "inbox", *ws)["data"]["items"]
    assert [i["event"] for i in items] == ["decision"]
    assert pw(capsys, "inbox", "--since", "9999", *ws)["data"]["count"] == 0
    everything = pw(capsys, "inbox", "--since", "", *ws)["data"]["items"]
    assert {"step", "decision"} <= {i["event"] for i in everything}
    status = pw(capsys, "status", "hero", *ws)["data"]["assets"][0]
    assert status["open_issues"] == 1 and status["waiting_for_decision"] is False
    history = pw(capsys, "history", "hero", "--limit", "1", *ws)["data"]["history"]
    assert history[0]["event"] == "decision"
