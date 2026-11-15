from pathlib import Path

import pytest

from pixelwright.workspace import SchemaError, Workspace, WorkspaceConfig, schema
from pixelwright.workspace.files import read_yaml
from pixelwright.workspace.gitignore import BEGIN, END


def test_init_creates_layout_and_reopens(tmp_path: Path) -> None:
    root = tmp_path / "game"
    Workspace.init(root)
    for rel in ("style/palettes", "style/references", "style/tests", "experiments", "assets"):
        assert (root / rel).is_dir()
    ws = Workspace.open(root)
    assert ws.config.canvas == {"width": 320, "height": 180}
    with pytest.raises(FileExistsError):
        Workspace.init(root)


def test_roles_map_to_game_paths(tmp_path: Path) -> None:
    config = WorkspaceConfig(
        roles={"style": "art/style", "assets": "art/src", "experiments": "tmp/exp", "cache": "c"},
        exports={"background": "game/art/backgrounds"},
    )
    ws = Workspace.init(tmp_path, config)
    ws.new_asset("bg-a", "background")
    assert (tmp_path / "art/src/bg-a/asset.yaml").is_file()
    assert Workspace.open(tmp_path).config.exports == {"background": "game/art/backgrounds"}


def test_config_rejects_bad_values() -> None:
    with pytest.raises(SchemaError, match="stages"):
        WorkspaceConfig(commit=["published"])
    with pytest.raises(SchemaError, match="inside"):
        WorkspaceConfig(exports={"sprite": "../outside"})


def test_asset_spec_validates_and_uses_default_canvas(ws: Workspace) -> None:
    ws.new_asset("chr-hero", "sprite", notes="hero")
    spec = schema.validate("asset", read_yaml(ws.path("assets") / "chr-hero/asset.yaml"))
    assert spec["canvas"] == {"width": 320, "height": 180}
    assert spec["notes"] == "hero"
    assert ws.assets() == ["chr-hero"]
    with pytest.raises(ValueError, match="kind"):
        ws.new_asset("chr-two", "hero")
    with pytest.raises(ValueError, match="kebab"):
        ws.new_asset("Bad_Id", "sprite")


def test_schema_refuses_newer_major_and_wrong_name() -> None:
    with pytest.raises(SchemaError, match="newer"):
        schema.validate("asset", {"schema": "pixelwright/asset@2"})
    with pytest.raises(SchemaError, match="expected schema"):
        schema.validate("asset", {"schema": "pixelwright/meta@1"})
    with pytest.raises(SchemaError, match="missing"):
        schema.validate("asset", {"schema": "pixelwright/asset@1"})


def _block(root: Path) -> list[str]:
    lines = (root / ".gitignore").read_text().splitlines()
    return lines[lines.index(BEGIN) + 1 : lines.index(END)]


def test_gitignore_follows_commit_stages(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    ws = Workspace.init(tmp_path)  # default commit: approved, final
    asset = ws.new_asset("bg-a", "background")
    v1 = asset.new_version("snap", {"image.png": b"x"})
    asset.new_version("snap", {"image.png": b"y"})
    asset.decide(v1, "approve")
    ws.refresh_gitignore()
    ws.refresh_gitignore()  # idempotent

    text = (tmp_path / ".gitignore").read_text()
    assert text.startswith("node_modules/\n")
    assert text.count(BEGIN) == 1
    assert _block(tmp_path) == [
        "/cache/",
        "/.pixelwright/secrets.toml",
        "/experiments/",
        "/assets/*/drafts/",
        "/assets/*/versions/*/",
        "!/assets/bg-a/versions/v0001/",
    ]


def test_gitignore_commit_everything_ignores_only_cache(tmp_path: Path) -> None:
    Workspace.init(tmp_path, WorkspaceConfig(commit=["experiment", "draft", "approved", "final"]))
    assert _block(tmp_path) == ["/cache/", "/.pixelwright/secrets.toml"]
