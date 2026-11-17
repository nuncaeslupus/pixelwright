from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from pixelwright.asset import Asset
from pixelwright.project import PROJECT_FILE, init_project, load_project


def _asset(tmp_path: Path, keep_all: bool) -> Asset:
    root = tmp_path / "art"
    init_project(root)
    if not keep_all:
        text = (
            (root / PROJECT_FILE)
            .read_text()
            .replace("keep_all_versions = true", "keep_all_versions = false")
        )
        (root / PROJECT_FILE).write_text(text)
    asset = Asset.create(load_project(root), "scenes/harbour")
    src = tmp_path / "in.png"
    Image.new("RGB", (4, 4)).save(src)
    asset.add_input(src)
    for i in range(6):
        asset.add_version(Image.new("RGB", (4, 4), (i, i, i)))
    return asset


@pytest.mark.parametrize("keep_all", [False, True])
def test_prune_setting_off_keeps_protected_versions(tmp_path: Path, keep_all: bool) -> None:
    asset = _asset(tmp_path, keep_all)
    asset.star("v003")
    asset.finish("v005")
    if keep_all:
        assert asset.versions() == ["v001", "v002", "v003", "v004", "v005", "v006"]
    else:
        assert asset.versions() == ["v001", "v003", "v005", "v006"]
    assert [p.name for p in asset.inputs()] == ["in.png"]
    assert (asset.path / "final.png").is_file()


def test_numbers_never_reused_after_prune(tmp_path: Path) -> None:
    asset = _asset(tmp_path, keep_all=False)
    asset.finish("v006")
    assert asset.versions() == ["v001", "v006"]
    assert asset.add_version(Image.new("RGB", (4, 4))) == "v007"
