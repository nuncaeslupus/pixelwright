from itertools import pairwise
from typing import Any

import numpy as np
from playwright.sync_api import expect

from pixelwright.io.aseprite import AseDocument, Cel, Frame, Layer, Tag, write_aseprite
from pixelwright.viewer.server import Viewer

DURATIONS = [100, 300, 200]


def animate(viewer: Viewer) -> None:
    """Give v0002 a layered file: 3 frames, each a different solid color, tag 'walk'."""
    frames = []
    for i, ms in enumerate(DURATIONS):
        px = np.zeros((12, 16, 4), np.uint8)
        px[...] = (60 * (i + 1), 40, 200 - 50 * i, 255)
        chunks: list[Any] = [Layer("body")] if i == 0 else []
        frames.append(Frame(duration=ms, chunks=[*chunks, Cel(0, pixels=px)]))
    frames[0].chunks.append([Tag("walk", 1, 2)])
    path = viewer.root / "assets/hero/versions/v0002/image.aseprite"
    write_aseprite(path, AseDocument(16, 12, frames=frames))


def test_play_uses_file_durations(page: Any, viewer: Viewer) -> None:
    animate(viewer)
    page.goto(viewer.url + "#/hero/v0002/play")
    expect(page.locator(".fr")).to_have_count(3)
    expect(page.locator(".fr").nth(1)).to_contain_text("300ms")
    page.keyboard.press(" ")
    page.wait_for_timeout(1900)  # a bit over three loops of 600 ms
    page.keyboard.press(" ")
    log = page.evaluate("window.pwPlayLog")
    frames = [e["frame"] for e in log]
    assert frames[:7] == [0, 1, 2, 0, 1, 2, 0]
    for prev, cur in pairwise(log):
        expected = DURATIONS[prev["frame"]]
        assert abs((cur["at"] - prev["at"]) - expected) < 60, (prev, cur)


def test_tag_steps_and_play_only_with_frames(page: Any, viewer: Viewer) -> None:
    page.goto(viewer.url + "#/hero/v0002")
    expect(page.get_by_role("button", name="Play", exact=True)).to_be_disabled()
    animate(viewer)
    page.reload()
    expect(page.get_by_role("button", name="Play", exact=True)).to_be_enabled()
    page.keyboard.press("p")
    expect(page.locator("#frame-label")).to_have_text("1 / 3")
    page.locator("#pl-tag").select_option("walk")
    expect(page.locator("#frame-label")).to_have_text("2 / 3")
    page.keyboard.press(".")
    expect(page.locator("#frame-label")).to_have_text("3 / 3")
    page.keyboard.press(".")  # stays inside the tag
    expect(page.locator("#frame-label")).to_have_text("3 / 3")
    page.keyboard.press(",")
    expect(page.locator(".fr.sel")).to_contain_text("300ms")
    page.get_by_role("button", name="Onion skin: previous frame at 30% (when paused)").click()
    expect(page.locator(".chip.on", has_text="Onion skin")).to_be_visible()
