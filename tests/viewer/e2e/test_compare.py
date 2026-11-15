from pathlib import Path
from typing import Any

from playwright.sync_api import expect

from pixelwright.cli import main
from pixelwright.viewer.server import Viewer
from pixelwright.workspace import Workspace


def three_versions(root: Path) -> None:
    """v0001 approved, v0002 rejected, v0003 = clean of v0002 (parent v0002), all checked."""
    w = ["--workspace", str(root)]
    assert main(["clean", "hero", *w]) == 0
    for v in ("v0001", "v0003"):
        assert main(["check", "hero", "--version", v, *w]) == 0
    asset = Workspace.open(root).asset("hero")
    asset.decide("v0001", "approve")
    asset.decide("v0002", "reject", note="noisy")


def test_compare_defaults_a_to_latest_approved(page: Any, viewer: Viewer) -> None:
    three_versions(viewer.root)
    page.goto(viewer.url + "#/hero/v0003/compare")
    expect(page.locator("#cv-a")).to_have_attribute("aria-label", "A v0001")
    expect(page.locator("#cv")).to_have_attribute("aria-label", "B v0003")
    expect(page.locator(".th.a")).to_contain_text("v0001")
    page.keyboard.press("2")
    expect(page.locator("#pane")).to_contain_text("v0001 → v0003")
    expect(page.locator("#changed")).to_be_visible()


def test_shift_click_picks_a_and_views_switch(page: Any, viewer: Viewer) -> None:
    three_versions(viewer.root)
    page.goto(viewer.url + "#/hero/v0003/compare")
    page.locator(".th", has_text="v0002").click(modifiers=["Shift"])
    expect(page.locator("#cv-a")).to_have_attribute("aria-label", "A v0002")
    assert page.url.endswith("#/hero/v0003/compare")
    for key, label in (("o", "B opacity"), ("w", "Swipe position")):
        page.keyboard.press(key)
        expect(page.locator("#cv-mix")).to_be_visible()
        expect(page.get_by_label(label)).to_be_visible()
    page.get_by_role("button", name="Difference").click()
    expect(page.locator(".seg .on")).to_have_text("Difference")
    page.locator(".th", has_text="v0001").click()
    assert page.url.endswith("#/hero/v0001/compare")


def test_compare_needs_two_versions(page: Any, viewer: Viewer, tmp_path: Path) -> None:
    w = ["--workspace", str(viewer.root)]
    assert main(["new", "solo", "--kind", "prop", *w]) == 0
    assert main(["attach", "solo", str(viewer.root.parent / "src.png"), *w]) == 0
    page.goto(viewer.url + "#/solo")
    expect(page.get_by_role("button", name="Compare")).to_be_disabled()
    page.goto(viewer.url + "#/hero")
    expect(page.get_by_role("button", name="Compare")).to_be_enabled()
    page.keyboard.press("c")
    expect(page.locator(".seg")).to_be_visible()
