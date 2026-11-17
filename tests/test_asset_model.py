from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
from PIL import Image

from pixelwright.asset import Asset, AssetError, list_assets, open_asset
from pixelwright.project import Project, init_project


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return init_project(tmp_path / "art", name="art")


def _img(color: tuple[int, int, int] = (10, 20, 30)) -> Image.Image:
    return Image.new("RGB", (8, 8), color)


def test_asset_files_plain_without_app_readable(project: Project, tmp_path: Path) -> None:
    asset = Asset.create(project, "scenes/harbour-night", brief="Harbour at night")
    src = tmp_path / "sketch.png"
    _img().save(src)
    asset.add_input(src)
    asset.add_version(_img())
    asset.add_version(_img((200, 0, 0)))
    asset.star("v001")
    asset.finish("v002")
    for f in sorted(p for p in asset.path.rglob("*") if p.is_file()):
        if f.suffix == ".toml":
            tomllib.loads(f.read_text(encoding="utf-8"))
        elif f.suffix == ".jsonl":
            for line in f.read_text(encoding="utf-8").splitlines():
                json.loads(line)
        elif f.suffix == ".png":
            with Image.open(f) as im:
                im.verify()
        else:
            pytest.fail(f"unexpected file type: {f}")
    meta = tomllib.loads((asset.path / "asset.toml").read_text())
    assert meta == {
        "brief": "Harbour at night",
        "state": "finished",
        "final": "v002",
        "starred": ["v001"],
    }


def test_versions_are_numbered_and_never_overwritten(project: Project) -> None:
    asset = Asset.create(project, "props/crate")
    assert asset.latest() is None
    assert [asset.add_version(_img()) for _ in range(3)] == ["v001", "v002", "v003"]
    before = asset.version_path("v001").read_bytes()
    asset.add_version(_img((0, 255, 0)))
    assert asset.version_path("v001").read_bytes() == before
    assert asset.versions() == ["v001", "v002", "v003", "v004"]


def test_add_input_keeps_existing(project: Project, tmp_path: Path) -> None:
    asset = Asset.create(project, "props/crate")
    src = tmp_path / "Crate.PNG"
    _img().save(src, format="PNG")
    a, b = asset.add_input(src), asset.add_input(src)
    assert (a.name, b.name) == ("Crate.png", "Crate-2.png")


def test_finish_copies_to_export_by_category(project: Project) -> None:
    asset = Asset.create(project, "scenes/harbour")
    asset.add_version(_img())
    target = asset.finish()
    assert target == project.export_dir / "scenes" / "harbour.png"
    assert target.read_bytes() == (asset.path / "final.png").read_bytes()
    asset.add_version(_img((1, 2, 3)))
    assert asset.meta().state == "review"  # new work reopens a finished asset


def test_finish_without_versions_fails(project: Project) -> None:
    with pytest.raises(AssetError, match="no version"):
        Asset.create(project, "props/empty").finish()


def test_bad_names_and_duplicates_rejected(project: Project) -> None:
    for bad in ("Scenes/x", "a/../b", "", "x y"):
        with pytest.raises(AssetError):
            Asset.create(project, bad)
    Asset.create(project, "props/crate")
    with pytest.raises(AssetError, match="exists"):
        Asset.create(project, "props/crate")


def test_star_unknown_version_rejected(project: Project) -> None:
    asset = Asset.create(project, "props/crate")
    with pytest.raises(AssetError, match="no version v009"):
        asset.star("v009")


def test_list_and_open_assets_with_category_settings(project: Project) -> None:
    (project.assets_dir / "scenes").mkdir()
    (project.assets_dir / "scenes" / "category.toml").write_text('palette = "night"\n')
    Asset.create(project, "scenes/harbour")
    Asset.create(project, "props/crate", kind="prop")
    assets = list_assets(project)
    assert [a.rel for a in assets] == ["props/crate", "scenes/harbour"]
    harbour = open_asset(project, project.assets_dir / "scenes" / "harbour")
    assert harbour.category == "scenes"
    assert harbour.settings().palette == "night"
    assert assets[0].meta().kind == "prop"


def test_bad_state_rejected(project: Project) -> None:
    asset = Asset.create(project, "props/crate")
    (asset.path / "asset.toml").write_text('state = "approved"\n')
    with pytest.raises(AssetError, match="state"):
        asset.meta()
