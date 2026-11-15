from typing import Any

import numpy as np
from playwright.sync_api import expect

from pixelwright.io.png import read_png
from pixelwright.viewer.server import Viewer
from pixelwright.workspace import Workspace


def to_cell(page: Any, x: int, y: int) -> dict[str, float]:
    """Canvas position of the centre of native pixel (x, y)."""
    zoom = int(page.locator("#zoom").input_value())
    return {"x": x * zoom + zoom / 2, "y": y * zoom + zoom / 2}


def drag(page: Any, a: tuple[int, int], b: tuple[int, int]) -> None:
    canvas = page.locator("#cv")
    box = canvas.bounding_box()
    pa, pb = to_cell(page, *a), to_cell(page, *b)
    page.mouse.move(box["x"] + pa["x"], box["y"] + pa["y"])
    page.mouse.down()
    page.mouse.move(box["x"] + pb["x"], box["y"] + pb["y"], steps=4)
    page.mouse.up()


def mask_of(viewer: Viewer, issue_id: str) -> Any:
    asset = Workspace.open(viewer.root).asset("hero")
    issue = asset.issue(issue_id)
    assert issue["author"] == "human" and issue["region"] == "mask"
    return read_png(asset.path / issue["file"]).to_rgba()[..., 0] > 127, issue


def open_mark(page: Any, viewer: Viewer) -> None:
    page.goto(viewer.url + "#/hero/v0002/mark")
    expect(page.get_by_role("toolbar", name="Mark tools")).to_be_visible()
    expect(page.locator("#cv")).to_be_visible()
    page.wait_for_timeout(300)  # first draw sets the zoom


def test_saved_mark_is_an_issue_in_native_pixels(page: Any, viewer: Viewer) -> None:
    open_mark(page, viewer)
    page.get_by_role("button", name="Rectangle").click()
    drag(page, (2, 3), (5, 6))
    # A rule reads by what it checks; the id is only the stored value.
    page.locator("#mk-rule").select_option(label="Orphan pixels and specks (R-PIX-3)")
    page.locator("#mk-note").fill("clean these clusters")
    page.get_by_role("button", name="Save as an issue").click()
    expect(page.locator(".issue.sel")).to_contain_text("clean these clusters")
    expect(page.locator(".issue.sel strong")).to_have_text("Orphan pixels and specks")
    issues = Workspace.open(viewer.root).asset("hero").issues()
    new = next(i for i in issues if i["author"] == "human")
    mask, issue = mask_of(viewer, new["id"])
    assert mask.shape == (12, 16)
    expected = np.zeros((12, 16), bool)
    expected[3:7, 2:6] = True
    assert (mask == expected).all()
    assert issue["rule"] == "R-PIX-3" and issue["version"] == "v0002" and issue["status"] == "open"


def test_brush_erase_undo_and_fill(page: Any, viewer: Viewer) -> None:
    open_mark(page, viewer)
    drag(page, (0, 0), (3, 0))  # brush, 1 px
    page.keyboard.press("e")
    drag(page, (3, 0), (3, 0))
    page.keyboard.press("Control+z")  # undo the erase
    page.keyboard.press("f")
    canvas = page.locator("#cv")
    canvas.click(position=to_cell(page, 10, 10))
    page.wait_for_timeout(300)
    page.locator("#mk-note").fill("mixed marks")
    page.keyboard.press("Control+s")
    expect(page.locator(".issue.sel")).to_contain_text("mixed marks")
    new = next(
        i for i in Workspace.open(viewer.root).asset("hero").issues() if i["author"] == "human"
    )
    mask, _ = mask_of(viewer, new["id"])
    assert mask[0, :4].all() and not mask[0, 4]
    image = Workspace.open(viewer.root).asset("hero").versions_dir / "v0002" / "image.png"
    rgba = read_png(image).to_rgba()
    filled = mask.copy()
    filled[0, :4] = False
    assert filled[10, 10] and (rgba[filled] == rgba[10, 10]).all()


def test_save_needs_a_region_and_a_note(page: Any, viewer: Viewer) -> None:
    open_mark(page, viewer)
    page.locator("#mk-note").fill("nothing marked")
    page.get_by_role("button", name="Save as an issue").click()
    expect(page.locator(".newissue .err")).to_have_text("Mark the region first.")
    drag(page, (1, 1), (1, 1))
    page.locator("#mk-note").fill("")
    page.get_by_role("button", name="Save as an issue").click()
    expect(page.locator(".newissue .err")).to_have_text("Say what is wrong there.")
    page.get_by_role("button", name="Discard the marks").click()
    assert all(i["author"] != "human" for i in Workspace.open(viewer.root).asset("hero").issues())
