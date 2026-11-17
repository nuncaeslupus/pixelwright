from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from pixelwright.asset import Asset
from pixelwright.core.checks import CheckResult
from pixelwright.issues import IssueError, IssueLog
from pixelwright.project import init_project
from pixelwright.rules import raise_check_issues

BG = (0, 0, 0, 255)
RED = (255, 0, 0, 255)
BLUE = (0, 0, 255, 255)


def _img(px: dict[tuple[int, int], tuple[int, int, int, int]] | None = None) -> Image.Image:
    im = Image.new("RGBA", (4, 4), BG)
    for xy, c in (px or {}).items():
        im.putpixel(xy, c)
    return im


def _pixels(asset: Asset, version: str) -> list[Any]:
    with Image.open(asset.version_path(version)) as im:
        return list(im.convert("RGBA").get_flattened_data())


@pytest.fixture
def asset(tmp_path: Path) -> Asset:
    a = Asset.create(init_project(tmp_path / "art"), "scenes/harbour")
    a.add_version(_img())
    return a


def test_fix_accept_writes_new_version(asset: Asset) -> None:
    log = IssueLog(asset)
    issue = log.raise_issue("Orphan pixel", author="script", kind="rule", rule="R-PIX-4")
    fix = log.propose_fix(issue.id, _img({(1, 1): RED}), by="script")
    before = asset.versions()
    version = log.accept([fix.id])
    assert asset.versions() == [*before, version]
    st = log.state()
    assert st.fixes[fix.id].state == "accepted"
    assert st.fixes[fix.id].result_version == version
    assert st.issues[issue.id].state == "fixed"
    assert _pixels(asset, version)[5] == RED


def test_several_fixes_accepted_together_make_one_version(asset: Asset) -> None:
    log = IssueLog(asset)
    a = log.raise_issue("left", author="ai", kind="critique")
    b = log.raise_issue("right", author="ai", kind="critique")
    fa = log.propose_fix(a.id, _img({(0, 0): RED}), by="ai")
    fb = log.propose_fix(b.id, _img({(3, 3): BLUE}), by="ai")
    version = log.accept([fa.id, fb.id])
    assert asset.versions() == ["v001", version]
    px = _pixels(asset, version)
    assert (px[0], px[15], px[5]) == (RED, BLUE, BG)


def test_undo_and_redo(asset: Asset) -> None:
    log = IssueLog(asset)
    issue = log.raise_issue("x", author="script")
    fix = log.propose_fix(issue.id, _img({(1, 1): RED}), by="script")
    v2 = log.accept([fix.id])
    v3 = log.undo()
    assert _pixels(asset, v3) == _pixels(asset, "v001")
    st = log.state()
    assert (st.fixes[fix.id].state, st.issues[issue.id].state) == ("proposed", "open")
    v4 = log.redo()
    assert _pixels(asset, v4) == _pixels(asset, v2)
    assert log.state().issues[issue.id].state == "fixed"
    with pytest.raises(IssueError, match="nothing to redo"):
        log.redo()


def test_undo_twice_redo_in_reverse_order(asset: Asset) -> None:
    log = IssueLog(asset)
    i1, i2 = log.raise_issue("a", author="ai"), log.raise_issue("b", author="ai")
    f1 = log.propose_fix(i1.id, _img({(0, 0): RED}), by="ai")
    v2 = log.accept([f1.id])
    f2 = log.propose_fix(i2.id, _img({(0, 0): RED, (3, 3): BLUE}), by="ai")
    log.accept([f2.id])
    log.undo()
    log.undo()
    first = log.redo()
    assert _pixels(asset, first) == _pixels(asset, v2)
    assert log.state().fixes[f1.id].state == "accepted"
    assert log.state().fixes[f2.id].state == "proposed"


def test_nothing_to_undo(asset: Asset) -> None:
    with pytest.raises(IssueError, match="nothing to undo"):
        IssueLog(asset).undo()


def test_reject_needs_reason_and_can_promote(asset: Asset) -> None:
    log = IssueLog(asset)
    issue = log.raise_issue("too dark", author="script", kind="rule", rule="R-VAL-1")
    with pytest.raises(IssueError, match="reason"):
        log.reject_issue(issue.id, " ")
    log.reject_issue(issue.id, "night scene, dark on purpose", promote=True)
    got = log.issue(issue.id)
    assert (got.state, got.reason, got.promote) == (
        "rejected",
        "night scene, dark on purpose",
        True,
    )


def test_reject_fix_keeps_issue_open(asset: Asset) -> None:
    log = IssueLog(asset)
    issue = log.raise_issue("x", author="ai")
    fix = log.propose_fix(issue.id, _img({(1, 1): RED}), by="ai")
    log.reject_fix(fix.id, "too bright")
    assert log.state().fixes[fix.id].state == "rejected"
    assert log.issue(issue.id).state == "open"
    with pytest.raises(IssueError, match="rejected"):
        log.accept([fix.id])


def test_request_and_reply_wait_on_ai(asset: Asset) -> None:
    log = IssueLog(asset)
    req = log.raise_issue(
        "Outline too thick", author="person", kind="request", target="ai",
        areas=[{"box": [0, 0, 2, 2]}],
    )  # fmt: skip
    assert [i.id for i in log.pending_for_ai()] == [req.id]
    log.propose_fix(req.id, _img({(0, 0): RED}), by="ai")
    assert log.pending_for_ai() == []
    log.reply(req.id, "Keep 5 strokes, just uneven", by="person")
    assert [i.id for i in log.pending_for_ai()] == [req.id]
    assert log.issue(req.id).replies[-1]["message"] == "Keep 5 strokes, just uneven"


def test_mark_fixed_for_outside_fix(asset: Asset) -> None:
    log = IssueLog(asset)
    issue = log.raise_issue("hand-fix the sail", author="person")
    log.mark_fixed(issue.id)
    assert log.issue(issue.id).state == "fixed"
    with pytest.raises(IssueError, match="not open"):
        log.mark_fixed(issue.id)


def test_log_is_plain_jsonl_and_fix_images_png(asset: Asset) -> None:
    log = IssueLog(asset)
    issue = log.raise_issue("x", author="script", kind="rule")
    fix = log.propose_fix(issue.id, _img({(1, 1): RED}), by="script")
    lines = (asset.path / "issues.jsonl").read_text().splitlines()
    assert [json.loads(line).get("event") for line in lines] == [None, "fix"]
    assert (asset.path / fix.image).is_file()


def test_validation(asset: Asset) -> None:
    log = IssueLog(asset)
    with pytest.raises(IssueError, match="author"):
        log.raise_issue("x", author="robot")
    with pytest.raises(IssueError, match="target"):
        log.raise_issue("x", author="person", target="human")
    issue = log.raise_issue("x", author="person")
    with pytest.raises(IssueError, match="size"):
        log.propose_fix(issue.id, Image.new("RGBA", (2, 2)), by="ai")
    with pytest.raises(IssueError, match="no fix"):
        log.accept(["f-missing"])
    with pytest.raises(IssueError, match="no issue"):
        log.reply("i-missing", "hi", by="person")


def _flag(rule: str) -> CheckResult:
    return CheckResult(check="orphans", rule=rule, status="fail", value=3, regions=((1, 1, 1, 1),))


def test_check_promoted_rejection_not_raised_again(asset: Asset) -> None:
    log = IssueLog(asset)
    [first] = raise_check_issues(log, "v001", [_flag("R-PIX-4")])
    assert raise_check_issues(log, "v001", [_flag("R-PIX-4")]) == []  # already open
    log.reject_issue(first.id, "dithered on purpose", promote=True, scope="category")
    assert raise_check_issues(log, "v001", [_flag("R-PIX-4")]) == []
    sibling = Asset.create(asset.project, "scenes/pier")
    sibling.add_version(_img())
    assert raise_check_issues(IssueLog(sibling), "v001", [_flag("R-PIX-4")]) == []
    other = Asset.create(asset.project, "props/crate")
    other.add_version(_img())
    assert len(raise_check_issues(IssueLog(other), "v001", [_flag("R-PIX-4")])) == 1
    rules = tomllib.loads((asset.project.root / "style" / "rules.toml").read_text())
    assert rules["promoted"] == [
        {"rule": "R-PIX-4", "scope": "category:scenes", "reason": "dithered on purpose"}
    ]


def test_rule_off_in_category_not_raised(asset: Asset) -> None:
    (asset.project.assets_dir / "scenes" / "category.toml").write_text('[checks]\n"R-X" = "off"\n')
    assert raise_check_issues(IssueLog(asset), "v001", [_flag("R-X")]) == []


def test_promote_needs_a_rule(asset: Asset) -> None:
    log = IssueLog(asset)
    issue = log.raise_issue("too dark", author="ai", kind="critique")
    with pytest.raises(IssueError, match="rule"):
        log.reject_issue(issue.id, "no", promote=True)
