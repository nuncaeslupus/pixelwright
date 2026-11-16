from pathlib import Path
from typing import Any

from playwright.sync_api import expect

from pixelwright.cli import main
from pixelwright.viewer.server import Viewer
from pixelwright.workspace import Workspace


def open_hero(page: Any) -> None:
    page.get_by_role("button", name="Open hero").click()
    expect(page.locator(".name")).to_have_text("hero")


def test_approve_writes_history_with_measurements(page: Any, viewer: Viewer) -> None:
    open_hero(page)
    page.get_by_role("button", name="Approve this version").first.click()
    page.locator("#note").fill("reads well")
    page.locator("#confirm").click()
    expect(page.locator(".hist")).to_contain_text("approved v0002")
    asset = Workspace.open(viewer.root).asset("hero")
    (decision,) = asset.decisions()
    assert decision["decision"] == "approve" and decision["note"] == "reads well"
    report = (asset.versions_dir / "v0002" / "report.json").read_text()
    assert decision["measurements"] and all(m["check"] in report for m in decision["measurements"])
    assert asset.stage("v0002") == "approved"


def test_reject_needs_a_note_and_esc_cancels(page: Any, viewer: Viewer) -> None:
    open_hero(page)
    page.keyboard.press("r")
    page.locator("#confirm").click()
    expect(page.locator("#pop-err")).to_contain_text("what should change")
    page.keyboard.press("Escape")
    expect(page.locator(".pop")).to_have_count(0)
    assert Workspace.open(viewer.root).asset("hero").decisions() == []
    page.keyboard.press("r")
    page.locator("#note").fill("too noisy")
    page.keyboard.press("Control+Enter")
    expect(page.locator(".hist")).to_contain_text("rejected v0002")


def test_ctrl_z_undoes_the_last_decision(page: Any, viewer: Viewer) -> None:
    Workspace.open(viewer.root).asset("hero").decide("v0002", "approve")
    open_hero(page)
    page.keyboard.press("Control+z")
    expect(page.locator("#pixel")).to_contain_text("Undid the approve of v0002")
    asset = Workspace.open(viewer.root).asset("hero")
    assert asset.history()[-1]["event"] == "decision_revert" and asset.stage("v0002") == "draft"


def test_issues_checks_and_versions(page: Any, viewer: Viewer) -> None:
    open_hero(page)
    expect(page.get_by_test_id("next-hint")).to_contain_text("Next:")
    issue = page.get_by_role("button", name="Show r-pix-3-1 on the image")
    expect(issue).to_contain_text("stray pixels")
    issue.click()
    expect(page.locator(".issue.sel")).to_have_count(1)
    page.keyboard.press("2")
    expect(page.locator(".crow").first).to_be_visible()
    page.keyboard.press("ArrowLeft")
    expect(page.locator(".meta")).to_contain_text("v0001")
    assert page.url.endswith("#/hero/v0001")


def test_url_opens_a_version_and_status_bar_reads_pixels(page: Any, viewer: Viewer) -> None:
    page.goto(viewer.url + "#/hero/v0002")
    expect(page.locator(".meta")).to_contain_text("v0002")
    canvas = page.locator("#cv")
    expect(canvas).to_be_visible()
    canvas.hover(position={"x": 2, "y": 2})
    expect(page.locator("#pixel")).to_contain_text("0, 0")
    expect(page.locator("#pixel")).to_contain_text("index")


def test_polling_shows_a_new_version(page: Any, viewer: Viewer, tmp_path: Path) -> None:
    open_hero(page)
    expect(page.locator(".th")).to_have_count(2)
    src = viewer.root.parent / "src.png"
    assert main(["attach", "hero", str(src), "--workspace", str(viewer.root)]) == 0
    expect(page.locator(".th")).to_have_count(3, timeout=8000)
    expect(page.locator("#bell .dot")).to_have_count(1)


def test_list_filters_theme_and_shortcuts(page: Any) -> None:
    expect(page.locator(".card")).to_have_count(1)
    page.locator("#f-find").fill("zzz")
    expect(page.locator(".card")).to_have_count(0)
    page.locator("#f-find").fill("her")
    expect(page.locator(".card")).to_have_count(1)
    before = page.evaluate("document.documentElement.dataset.theme")
    page.locator("body").click()
    page.keyboard.press("t")
    assert page.evaluate("document.documentElement.dataset.theme") != before
    page.keyboard.press("?")
    expect(page.locator("#keys")).to_be_visible()


def test_views_include_a_quarter_size_thumb(page: Any, viewer: Viewer) -> None:
    page.goto(viewer.url + "#/hero/v0002")
    expect(page.locator("#cv")).to_be_visible()
    page.wait_for_timeout(300)
    full = page.evaluate("document.getElementById('cv').width")
    page.locator("#view").select_option("thumb")
    page.wait_for_timeout(300)
    small = page.evaluate("document.getElementById('cv').width")
    assert small < full and small % 16 == 0


def test_help_explains_the_loop_and_the_rule_codes(page: Any) -> None:
    page.locator("body").click()
    page.keyboard.press("?")
    keys = page.locator("#keys")
    expect(keys).to_be_visible()
    # The loop, with this window placed in it, and the codes spelled out.
    expect(keys).to_contain_text("You are here")
    expect(keys).to_contain_text("Nothing here edits an image")
    expect(keys).to_contain_text("R-PIX-3")
    expect(keys).to_contain_text("Orphan pixels and specks")
    expect(keys).to_contain_text("Keyboard shortcuts")
