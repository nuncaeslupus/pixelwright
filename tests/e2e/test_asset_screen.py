from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from PIL import Image
from playwright.sync_api import expect

from pixelwright.app.api import AppApi
from pixelwright.asset import Asset
from pixelwright.issues import IssueLog
from pixelwright.project import Project


@pytest.fixture
def harbour(app_project: Project) -> Asset:
    (app_project.assets_dir / "scenes" / "category.toml").write_text(
        "[canvas]\nwidth = 32\nheight = 18\n"
    )
    return Asset(app_project, app_project.assets_dir / "scenes" / "harbour")


def _open(open_app: Callable[[AppApi], Any], project: Project) -> Any:
    page = open_app(AppApi(project.root))
    page.get_by_role("button", name="Open scenes/harbour").click()
    expect(page.get_by_role("button", name="Back")).to_be_visible()
    return page


def _with_fix(asset: Asset, message: str = "Orphan pixel", color: int = 255) -> str:
    log = IssueLog(asset)
    issue = log.raise_issue(message, author="script", kind="rule", rule="R-PIX-4",
                            areas=[{"box": [1, 1, 2, 2]}])  # fmt: skip
    im = Image.open(asset.version_path(asset.latest() or "v001")).convert("RGBA")
    im.putpixel((1, 1), (color, 0, 0, 255))
    return log.propose_fix(issue.id, im, by="script").id


def test_asset_screen_request_creates_open_issue(
    app_project: Project, harbour: Asset, open_app: Callable[[AppApi], Any]
) -> None:
    page = _open(open_app, app_project)
    page.get_by_role("group", name="Tool").get_by_title("Select areas (S)").click()
    img = page.locator(".canvas .pic img")
    box = img.bounding_box()
    page.mouse.move(box["x"] + 5, box["y"] + 5)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 3, box["y"] + box["height"] / 2)
    page.mouse.up()
    expect(page.get_by_text("1 area(s) attached")).to_be_visible()
    page.get_by_label("Ask the AI").fill("Outline too thick here")
    page.get_by_role("button", name="Send to the AI").click()
    expect(page.locator(".issue")).to_contain_text("waiting on the AI")
    (issue,) = IssueLog(harbour).state().issues.values()
    assert (issue.state, issue.target, issue.kind) == ("open", "ai", "request")
    assert issue.message == "Outline too thick here" and len(issue.areas) == 1


def test_accept_fix_then_undo_and_redo(
    app_project: Project, harbour: Asset, open_app: Callable[[AppApi], Any]
) -> None:
    _with_fix(harbour)
    page = _open(open_app, app_project)
    page.get_by_role("button", name="Accept fix").click()
    expect(page.get_by_role("button", name="Finish with v002")).to_be_visible()
    page.get_by_title("Undo (Ctrl+Z)").click()
    expect(page.get_by_role("button", name="Finish with v003")).to_be_visible()
    expect(page.get_by_role("button", name="Accept fix")).to_be_visible()
    page.get_by_title("Redo (Ctrl+Shift+Z)").click()
    expect(page.get_by_role("button", name="Finish with v004")).to_be_visible()


def test_accept_several_fixes_together(
    app_project: Project, harbour: Asset, open_app: Callable[[AppApi], Any]
) -> None:
    _with_fix(harbour, "a", 200)
    _with_fix(harbour, "b", 100)
    page = _open(open_app, app_project)
    for cb in page.locator(".pick input, input.pick").all():
        cb.check()
    page.get_by_role("button", name="Accept 2 fixes together").click()
    expect(page.get_by_role("button", name="Finish with v002")).to_be_visible()
    assert harbour.versions() == ["v001", "v002"]


def test_reject_fix_and_reply(
    app_project: Project, harbour: Asset, open_app: Callable[[AppApi], Any]
) -> None:
    fix_id = _with_fix(harbour)
    page = _open(open_app, app_project)
    page.get_by_role("button", name="Reject…").click()
    page.get_by_label("Why not? (the AI reads this)").fill("too bright")
    page.get_by_role("button", name="Send", exact=True).click()
    expect(page.get_by_role("button", name="Mark fixed")).to_be_visible()
    assert IssueLog(harbour).state().fixes[fix_id].state == "rejected"
    page.get_by_role("button", name="Reply…").click()
    page.get_by_label("Reply to the AI").fill("keep 5 strokes")
    page.get_by_role("button", name="Send", exact=True).click()
    expect(page.locator(".issue .thread")).to_contain_text("keep 5 strokes")


def test_finish_star_and_compare(
    app_project: Project, harbour: Asset, open_app: Callable[[AppApi], Any]
) -> None:
    _with_fix(harbour)
    page = _open(open_app, app_project)
    page.locator(".issue").first.click()
    expect(page.get_by_text("hold Space or the image to compare")).to_be_visible()
    page.get_by_role("button", name="Side by side").click()
    expect(page.locator(".canvas .pic")).to_have_count(2)
    page.get_by_title("Keep this version").first.click()
    expect(page.get_by_title("Keep this version").first).to_have_text("★")
    page.get_by_role("button", name="Finish with v001").click()
    expect(page.locator(".atop .chip")).to_have_text("Finished")
    assert (app_project.root / "export" / "scenes" / "harbour.png").is_file()
    assert harbour.meta().starred == ["v001"]
