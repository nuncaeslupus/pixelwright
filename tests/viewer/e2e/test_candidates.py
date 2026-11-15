from pathlib import Path
from typing import Any

from playwright.sync_api import expect

from pixelwright.cli import main
from pixelwright.fixtures import tour
from pixelwright.io.png import encode_png
from pixelwright.viewer.server import Viewer
from pixelwright.workspace import Workspace


def three_candidates(root: Path) -> None:
    w = ["--workspace", str(root)]
    (root / "replay").mkdir()
    for name, image in (("a", tour.painted()), ("b", tour.sketch()), ("c", tour.scene())):
        (root / "replay" / f"{name}.png").write_bytes(encode_png(image))
    assert main(["new", "bg", "--kind", "background", "--canvas", "160x90", *w]) == 0
    gen = ["generate", "bg", "--provider", "replay", "--prompt", "dusk", "--n", "3", *w]
    assert main(gen) == 0


def test_compare_shows_candidates_of_one_generate(page: Any, viewer: Viewer) -> None:
    three_candidates(viewer.root)
    page.goto(viewer.url + "#/bg/v0002/compare")
    for v in ("v0001", "v0002", "v0003"):
        expect(page.get_by_label(f"Candidate {v}")).to_be_visible()
    boxes = [page.get_by_label(f"Candidate {v}").bounding_box() for v in ("v0001", "v0002")]
    assert abs(boxes[0]["y"] - boxes[1]["y"]) < 2 and boxes[0]["x"] < boxes[1]["x"]  # side by side
    page.get_by_role("button", name="Pick v0002, reject the other candidates").click()
    page.wait_for_function("() => location.hash === '#/bg/v0002/compare'")
    asset = Workspace.open(viewer.root).asset("bg")
    for _ in range(50):  # the two rejections land one after the other
        if len(asset.decisions()) == 2:
            break
        page.wait_for_timeout(100)
    picked = asset.decisions()
    assert [(d["version"], d["decision"]) for d in picked] == [
        ("v0001", "reject"),
        ("v0003", "reject"),
    ]


def test_no_candidates_view_without_siblings(page: Any, viewer: Viewer) -> None:
    page.goto(viewer.url + "#/hero/v0002/compare")
    expect(page.locator("#cv-a")).to_be_visible()
    expect(page.get_by_role("button", name="Candidates")).to_have_count(0)
