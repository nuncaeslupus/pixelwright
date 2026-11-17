from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from pixelwright.project import (
    PROJECT_FILE,
    ProjectError,
    find_project,
    init_project,
    load_project,
    resolve_settings,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "art"
    init_project(root, name="my-art")
    return root


def test_init_project_writes_plain_toml_and_folders(project_root: Path) -> None:
    data = tomllib.loads((project_root / PROJECT_FILE).read_text())
    assert data["project"] == {"name": "my-art", "keep_all_versions": True, "export": "export"}
    assert data["palettes"]["default"] == "main"
    assert (project_root / "assets").is_dir()
    assert (project_root / "style" / "palettes").is_dir()


def test_init_project_refuses_existing(project_root: Path) -> None:
    with pytest.raises(ProjectError, match="already"):
        init_project(project_root)


def test_load_project_round_trip(project_root: Path) -> None:
    project = load_project(project_root)
    assert project.name == "my-art"
    assert project.canvas == {"width": 320, "height": 180}
    assert project.export_dir == project_root.resolve() / "export"


def test_settings_asset_in_category_uses_category_palette(project_root: Path) -> None:
    _write(project_root / "assets" / "scenes" / "category.toml", 'palette = "night"\n')
    asset = project_root / "assets" / "scenes" / "harbour-night"
    asset.mkdir(parents=True)
    settings = resolve_settings(load_project(project_root), asset)
    assert settings.palette == "night"
    assert settings.palettes == ("night",)


def test_settings_nearest_folder_wins(project_root: Path) -> None:
    _write(
        project_root / PROJECT_FILE,
        '[project]\nname = "x"\n[canvas]\nwidth = 320\nheight = 180\n'
        '[palettes]\ndefault = "main"\n[rules]\n"R-PIX-4" = "warn"\n',
    )
    _write(
        project_root / "assets" / "characters" / "category.toml",
        'kind = "sprite"\npalette = "chars"\n[canvas]\nwidth = 32\nheight = 32\n'
        '[checks]\n"R-PIX-4" = "error"\n',
    )
    _write(
        project_root / "assets" / "characters" / "hero" / "asset.toml",
        'palettes = ["chars", "night"]\n[canvas]\nheight = 48\n',
    )
    project = load_project(project_root)
    hero = resolve_settings(project, project_root / "assets" / "characters" / "hero")
    assert hero.kind == "sprite"
    assert hero.palettes == ("chars", "night")
    assert hero.canvas == {"width": 32, "height": 48}
    assert hero.checks == {"R-PIX-4": "error"}
    other = resolve_settings(project, project_root / "assets" / "props" / "crate")
    assert other.palette == "main"
    assert other.kind is None
    assert other.checks == {"R-PIX-4": "warn"}


def test_settings_outside_assets_rejected(project_root: Path) -> None:
    with pytest.raises(ProjectError, match="not under"):
        resolve_settings(load_project(project_root), project_root / "style")


def test_bad_canvas_rejected(project_root: Path) -> None:
    _write(project_root / "assets" / "scenes" / "category.toml", "[canvas]\nwidth = -3\n")
    with pytest.raises(ProjectError, match="canvas"):
        resolve_settings(load_project(project_root), project_root / "assets" / "scenes")


def test_bad_rule_level_rejected(project_root: Path) -> None:
    _write(project_root / PROJECT_FILE, '[project]\nname = "x"\n[rules]\n"R-1" = "loud"\n')
    with pytest.raises(ProjectError, match="rules"):
        load_project(project_root)


def test_find_project_from_an_image_inside(project_root: Path) -> None:
    image = project_root / "assets" / "scenes" / "a" / "inputs" / "sketch.png"
    _write(image, "")
    assert find_project(image) == project_root.resolve()


def test_find_project_none(tmp_path: Path) -> None:
    with pytest.raises(ProjectError, match=r"no pixelwright\.toml"):
        find_project(tmp_path)


def test_categories_and_palettes_listed(project_root: Path) -> None:
    for name in ("scenes", "characters"):
        (project_root / "assets" / name).mkdir()
    _write(project_root / "style" / "palettes" / "night.gpl", "GIMP Palette\n")
    project = load_project(project_root)
    assert project.categories() == ["characters", "scenes"]
    assert project.palette_names() == ["night"]


def test_absolute_export_kept(project_root: Path, tmp_path: Path) -> None:
    target = tmp_path / "engine" / "art"
    _write(project_root / PROJECT_FILE, f"[project]\nname = 'x'\nexport = '{target}'\n")
    assert load_project(project_root).export_dir == target
