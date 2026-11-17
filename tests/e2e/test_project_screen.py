from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image
from playwright.sync_api import expect

from pixelwright.app.api import AppApi
from pixelwright.project import Project


def test_project_screen_shows_next_step(
    app_project: Project, open_app: Callable[[AppApi], Any]
) -> None:
    page = open_app(AppApi(app_project.root))
    cards = page.locator(".asset")
    expect(cards).to_have_count(3)
    for i in range(3):
        expect(cards.nth(i).locator(".next .step")).to_have_count(1)
        expect(cards.nth(i).locator(".next .step")).not_to_be_empty()
    expect(page.get_by_role("button", name="Open scenes/pier")).to_contain_text("Add an image")


def test_filters_by_actor_state_and_category(
    app_project: Project, open_app: Callable[[AppApi], Any]
) -> None:
    page = open_app(AppApi(app_project.root))
    side = page.get_by_role("navigation", name="Filters")
    side.get_by_role("button", name="scenes").click()
    expect(page.locator(".asset")).to_have_count(2)
    side.get_by_role("button", name="In review").click()
    expect(page.locator(".asset")).to_have_count(2)
    side.get_by_role("button", name="All assets").click()
    expect(page.locator(".asset")).to_have_count(3)


def test_add_images_into_a_new_category(
    app_project: Project, open_app: Callable[[AppApi], Any], tmp_path: Path
) -> None:
    img = tmp_path / "Barrel 2.png"
    Image.new("RGB", (64, 36), (200, 100, 50)).save(img)
    api = AppApi(app_project.root)
    api.bind_file_picker(lambda: [str(img)])
    page = open_app(api)
    page.get_by_role("button", name="+ Add images").click()
    page.get_by_label("New category").fill("barrels")
    page.get_by_role("button", name="Choose images…").click()
    expect(page.get_by_role("button", name="Open barrels/barrel-2")).to_be_visible()
    assert (app_project.assets_dir / "barrels" / "barrel-2" / "inputs" / "Barrel 2.png").is_file()


def test_image_saved_into_category_folder_is_picked_up(
    app_project: Project, open_app: Callable[[AppApi], Any]
) -> None:
    page = open_app(AppApi(app_project.root))
    expect(page.locator(".asset")).to_have_count(3)
    Image.new("RGB", (64, 36)).save(app_project.assets_dir / "props" / "lamp.png")
    expect(page.get_by_role("button", name="Open props/lamp")).to_be_visible(timeout=8000)
    assert not (app_project.assets_dir / "props" / "lamp.png").exists()


def test_review_all_new_asks_the_ai(
    app_project: Project, open_app: Callable[[AppApi], Any]
) -> None:
    page = open_app(AppApi(app_project.root))
    page.get_by_role("button", name="Review all new with AI · 2").click()
    expect(page.get_by_role("button", name="Open props/crate")).to_contain_text("Waiting on the AI")


def test_start_screen_when_no_project(open_app: Callable[[AppApi], Any]) -> None:
    page = open_app(AppApi())
    expect(page.get_by_role("button", name="Open a project folder…")).to_be_visible()
