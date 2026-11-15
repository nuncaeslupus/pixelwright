from typing import Any

import numpy as np
from playwright.sync_api import expect

from pixelwright.io.aseprite import AseDocument, Cel, Frame, Layer, write_aseprite
from pixelwright.viewer.server import Viewer

UNTITLED = """() => [...document.querySelectorAll('button, select, input')]
  .filter((el) => !el.title && !el.closest('[title]'))
  .map((el) => el.outerHTML.slice(0, 120))"""
NO_SHORTCUT = """() => [...document.querySelectorAll('#app button[data-action]')]
  .filter((el) => !/\\(.+\\)$/.test(el.title))
  .map((el) => el.dataset.action)"""
# Buttons that act on one item of a list (a card, an issue, an inbox line, a menu entry)
# are reached with Tab and Enter; they need a title, not their own shortcut.
LIST_ITEMS = {"open", "issue", "open-item", "seen", "mk-discard", "cancel"}


def animate(viewer: Viewer) -> None:
    px = np.full((12, 16, 4), 255, np.uint8)
    frames = [Frame(duration=100, chunks=[Layer("body"), Cel(0, pixels=px)])]
    frames.append(Frame(duration=100, chunks=[Cel(0, pixels=px)]))
    write_aseprite(
        viewer.root / "assets/hero/versions/v0002/image.aseprite",
        AseDocument(16, 12, frames=frames),
    )


def controls_ok(page: Any) -> None:
    assert page.evaluate(UNTITLED) == []
    assert set(page.evaluate(NO_SHORTCUT)) <= LIST_ITEMS


def test_every_control_has_a_title_and_shortcut(page: Any, viewer: Viewer) -> None:
    animate(viewer)
    page.goto(viewer.url)
    expect(page.locator(".card")).to_have_count(1)
    controls_ok(page)
    page.get_by_role("button", name="Open hero").focus()
    page.keyboard.press("Enter")
    expect(page.locator(".name")).to_have_text("hero")
    modes = (
        ("c", "Compare", "Swipe"),
        ("m", "Mark", "Brush"),
        ("p", "Play", "Onion skin"),
        ("l", "Look", "Approve"),
    )
    for key, mode, shortcut in modes:
        page.locator("body").press(key)
        expect(page.locator(".modes .on")).to_have_text(mode)
        page.wait_for_timeout(150)
        controls_ok(page)
        page.keyboard.press("?")
        expect(page.locator("#keys")).to_be_visible()
        expect(page.locator("#keys")).to_contain_text(shortcut)
        page.keyboard.press("Escape")
        expect(page.locator("#keys")).not_to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator(".card")).to_have_count(1)


def test_both_themes_render(page: Any, viewer: Viewer) -> None:
    page.goto(viewer.url + "#/hero/v0002")
    expect(page.locator("#cv")).to_be_visible()
    colors = {}
    for _ in range(2):
        theme = page.evaluate("document.documentElement.dataset.theme")
        colors[theme] = page.evaluate("getComputedStyle(document.body).backgroundColor")
        page.get_by_role("button", name="Light or dark theme").click()
    assert set(colors) == {"light", "dark"} and colors["light"] != colors["dark"]
    page.get_by_role("button", name="Light or dark theme").click()
    chosen = page.evaluate("document.documentElement.dataset.theme")
    page.reload()  # the choice is remembered
    assert page.evaluate("document.documentElement.dataset.theme") == chosen
