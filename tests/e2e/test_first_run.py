from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from playwright.sync_api import expect

from pixelwright.app import recent
from pixelwright.app.api import AppApi
from pixelwright.project import Project


def test_first_launch_opens_sample_project(
    open_app: Callable[[AppApi], Any], tmp_path: Path
) -> None:
    page = open_app(AppApi())
    expect(page.locator(".asset")).to_have_count(2)
    expect(page.locator("#crumb")).to_contain_text("sample")
    for i in range(2):
        expect(page.locator(".asset").nth(i).locator(".next .step")).not_to_be_empty()
    sample = tmp_path / "data" / "pixelwright" / "sample"
    assert recent.load_recent() == [str(sample.resolve())]
    page.get_by_role("button", name="Open scenes/house", exact=True).click()
    expect(page.get_by_role("button", name="Back")).to_be_visible()


def test_later_launch_shows_recent_projects(
    app_project: Project, open_app: Callable[[AppApi], Any], tmp_path: Path
) -> None:
    recent.remember(app_project.root)
    page = open_app(AppApi())
    expect(page.get_by_role("button", name="Open a project folder…")).to_be_visible()
    expect(page.locator(".recent")).to_have_count(1)
    assert not (tmp_path / "data" / "pixelwright" / "sample").exists()
