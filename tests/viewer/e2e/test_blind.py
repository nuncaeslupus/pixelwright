from typing import Any

from playwright.sync_api import expect

from pixelwright.fixtures.bench import bench_workspace
from pixelwright.viewer.server import Viewer


def test_blind_page_hides_provider_names(page: Any, viewer: Viewer) -> None:
    out = bench_workspace(viewer.root)
    urls: list[str] = []
    page.on("request", lambda r: urls.append(r.url))
    page.goto(viewer.url + "blind?b=try")
    expect(page.get_by_role("img", name="Left image")).to_be_visible()
    expect(page.get_by_role("img", name="Right image")).to_be_visible()
    shown = page.content() + " ".join(urls)
    for leak in ("replay", "bench-", "full", "light", "/assets/"):
        assert leak not in shown, leak
    expect(page.locator("#left")).to_contain_text("8 pairs left")
    page.keyboard.press("1")
    expect(page.locator("#left")).to_contain_text("7 pairs left")
    lines = (out / "human_pairs.jsonl").read_text().splitlines()
    assert len(lines) == 1 and '"winner": "a"' in lines[0]
