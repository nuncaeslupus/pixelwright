from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from pixelwright.asset import Asset
from pixelwright.bridge import hook_message, pending_requests, wait_for_requests
from pixelwright.cli import main
from pixelwright.issues import IssueLog
from pixelwright.project import Project, init_project

LATENCY_BUDGET_S = 10.0


@pytest.fixture
def project(tmp_path: Path) -> Project:
    project = init_project(tmp_path / "art")
    asset = Asset.create(project, "scenes/harbour")
    asset.add_version(Image.new("RGBA", (4, 4)))
    return project


def _log(project: Project) -> IssueLog:
    return IssueLog(Asset(project, project.assets_dir / "scenes" / "harbour"))


def _cli(capsys: pytest.CaptureFixture[str], root: Path, *argv: str) -> dict[str, Any]:
    assert main([*argv, "--workspace", str(root), "--json"]) == 0
    env: dict[str, Any] = json.loads(capsys.readouterr().out)
    return env


def test_wait_request_written_returns_within_latency(project: Project) -> None:
    proc = subprocess.Popen(
        [sys.executable, "-c", "from pixelwright.cli import main; raise SystemExit(main())",
         "wait", "--workspace", str(project.root), "--timeout", "30", "--poll", "0.2", "--json"],
        stdout=subprocess.PIPE,
        text=True,
    )  # fmt: skip
    try:
        time.sleep(1.0)  # pw wait is now blocked on an empty queue
        assert proc.poll() is None
        written = time.monotonic()
        issue = _log(project).raise_issue(
            "Outline too thick", author="person", kind="request", target="ai"
        )
        out, _ = proc.communicate(timeout=LATENCY_BUDGET_S + 5)
        wait_latency_seconds = time.monotonic() - written
    finally:
        proc.kill()
    assert proc.returncode == 0
    assert wait_latency_seconds <= LATENCY_BUDGET_S
    requests = json.loads(out)["data"]["requests"]
    assert [r["issue"] for r in requests] == [issue.id]
    assert requests[0]["asset"] == "scenes/harbour"


def test_wait_returns_all_pending_without_blocking(project: Project) -> None:
    log = _log(project)
    a = log.raise_issue("a", author="person", kind="request", target="ai")
    b = log.raise_issue("b", author="person", kind="request", target="ai")
    log.raise_issue("not for the AI", author="script", kind="rule")
    got = wait_for_requests(project, timeout=1, poll=0.05)
    assert {r["issue"] for r in got} == {a.id, b.id}


def test_wait_times_out_empty(project: Project) -> None:
    start = time.monotonic()
    assert wait_for_requests(project, timeout=0.3, poll=0.05) == []
    assert time.monotonic() - start < 2


def test_answered_request_no_longer_pending(project: Project) -> None:
    log = _log(project)
    req = log.raise_issue("x", author="person", kind="request", target="ai")
    log.propose_fix(req.id, Image.new("RGBA", (4, 4), (9, 9, 9, 255)), by="ai")
    assert pending_requests(project) == []


def test_requests_cli_and_hook(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    assert _cli(capsys, project.root, "requests")["data"]["requests"] == []
    assert hook_message(project) == ""
    _log(project).raise_issue("x", author="person", kind="request", target="ai")
    env = _cli(capsys, project.root, "requests", "--hook")
    assert env["data"]["message"].startswith("pixelwright: 1 request ")
    assert len(_cli(capsys, project.root, "requests")["data"]["requests"]) == 1
