import json
from pathlib import Path

import pytest

from pixelwright.core.palette import Color, Palette
from pixelwright.io.palette_io import write_palette
from pixelwright.workspace import SchemaError, Workspace, schema
from pixelwright.workspace.files import read_yaml
from pixelwright.workspace.style import StyleGuide, bump_style, load_palettes, load_style


def test_style_bump_records_version_on_new_assets(ws: Workspace) -> None:
    style_dir = ws.path("style")
    before = ws.new_asset("bg-old", "background")
    assert before.spec()["style_version"] == 1

    new = bump_style(style_dir, {"outline": {"sprites": "selout"}}, note="selout for sprites")
    after = ws.new_asset("chr-new", "sprite")

    assert new.version == 2
    assert after.spec()["style_version"] == 2
    assert ws.stale_assets() == [("bg-old", 1)]

    failures = 0
    for path in (style_dir / "style.yaml", style_dir / "versions/style-v0001.yaml"):
        try:
            schema.validate("style", read_yaml(path))
        except SchemaError:
            failures += 1
    lines = (style_dir / "history.jsonl").read_text().splitlines()
    for line in lines:
        try:
            schema.validate("history", json.loads(line))
        except SchemaError:
            failures += 1
    assert failures == 0
    event = json.loads(lines[-1])
    assert (event["event"], event["from"], event["to"]) == ("style_bump", 1, 2)
    assert load_style(style_dir).outline == {"sprites": "selout"}
    old = schema.validate("style", read_yaml(style_dir / "versions/style-v0001.yaml"))
    assert old["outline"] == {}


def test_bump_refuses_explicit_version_and_unknown_keys(ws: Workspace) -> None:
    with pytest.raises(ValueError, match="version"):
        bump_style(ws.path("style"), {"version": 9})
    with pytest.raises(SchemaError, match="unknown"):
        bump_style(ws.path("style"), {"colour": "red"})
    assert ws.style().version == 1


def test_style_palettes_load(tmp_path: Path) -> None:
    ws = Workspace.init(tmp_path)
    style_dir = ws.path("style")
    write_palette(style_dir / "palettes/night.gpl", Palette([Color(1, 2, 3, "ink")], name="night"))
    bump_style(style_dir, {"palettes": ["palettes/night.gpl"]})
    palettes = load_palettes(style_dir, ws.style())
    assert palettes["palettes/night.gpl"].name == "night"


def test_default_style_guide_roundtrip() -> None:
    guide = StyleGuide(palettes=["palettes/a.gpl"], notes="moody")
    assert StyleGuide.from_dict(guide.to_dict()) == guide
