import json
from pathlib import Path

import pytest

from pixelwright.workspace import Workspace, schema
from pixelwright.workspace.files import read_yaml, sha256_bytes


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


def test_new_version_is_immutable_and_logged(ws: Workspace) -> None:
    asset = ws.new_asset("bg-harbour-night", "background")
    lines_before = len(asset.history_path.read_text().splitlines())

    v1 = asset.new_version("snap", {"image.png": b"one"}, params={"scale": 4})
    v1_files = _snapshot(asset.versions_dir / v1)
    lines_after_v1 = asset.history_path.read_text().splitlines()
    v2 = asset.new_version("quantize", {"image.png": b"two"}, parent=v1, seed=7)

    assert (v1, v2) == ("v0001", "v0002")
    assert _snapshot(asset.versions_dir / v1) == v1_files  # earlier version untouched
    assert len(lines_after_v1) == lines_before + 1
    history = asset.history_path.read_text().splitlines()
    assert history[: len(lines_after_v1)] == lines_after_v1  # append-only
    assert len(history) == len(lines_after_v1) + 1

    failures = 0
    for version in (v1, v2):
        try:
            schema.validate("meta", read_yaml(asset.versions_dir / version / "meta.yaml"))
        except schema.SchemaError:
            failures += 1
    for line in history:
        try:
            schema.validate("history", json.loads(line))
        except schema.SchemaError:
            failures += 1
    assert failures == 0

    meta2 = asset.meta(v2)
    assert meta2["parent"] == v1
    assert meta2["seed"] == 7
    assert meta2["outputs"] == {"image.png": sha256_bytes(b"two")}
    last = json.loads(history[-1])
    assert (last["event"], last["version"], last["step"]) == ("step", v2, "quantize")


def test_no_temp_folders_left_after_failure(ws: Workspace) -> None:
    asset = ws.new_asset("chr-hero", "sprite")
    with pytest.raises(ValueError, match="file name"):
        asset.new_version("snap", {"../escape.png": b"x"})
    assert list(asset.versions_dir.iterdir()) == []


def test_parent_must_exist(ws: Workspace) -> None:
    asset = ws.new_asset("chr-hero", "sprite")
    with pytest.raises(FileNotFoundError):
        asset.new_version("snap", {"image.png": b"x"}, parent="v0009")


def test_decisions_drive_stage_and_are_logged(ws: Workspace) -> None:
    asset = ws.new_asset("fx-torch", "effect")
    v1 = asset.new_version("snap", {"image.png": b"x"})
    assert asset.stage(v1) == "draft"
    asset.decide(v1, "approve", note="good")
    assert asset.stage(v1) == "approved"
    asset.decide(v1, "reject", author="claude")
    assert asset.stage(v1) == "draft"
    assert asset.meta(v1)["stage"] == "draft"  # meta never rewritten
    with pytest.raises(ValueError):
        asset.decide(v1, "maybe")


def test_masks_are_indexed(ws: Workspace) -> None:
    asset = ws.new_asset("bg-dock", "background")
    asset.add_mask("focal", b"png", rule="focal-contrast", author="check")
    entries = asset.masks()
    assert [(m["id"], m["file"], m["author"]) for m in entries] == [
        ("focal", "masks/focal.png", "check")
    ]
    with pytest.raises(FileExistsError):
        asset.add_mask("focal", b"png")
