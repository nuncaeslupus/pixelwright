import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pixelwright.asset import Asset, open_asset
from pixelwright.io import aseprite_cli
from pixelwright.project import init_project, load_project


@pytest.fixture
def project(tmp_path: Path) -> Path:
    project = init_project(tmp_path / "art")
    Asset.create(project, "sprites/hero")
    rgba = np.zeros((8, 8, 4), np.uint8)
    rgba[2:6, 2:6] = (200, 40, 40, 255)
    Image.fromarray(rgba, "RGBA").save(tmp_path / "hero.png")
    return project.root


def test_scripts_ship_with_the_plugin() -> None:
    for name in ("pixelwright.lua", "send_to_pixelwright.lua", "load_version.lua"):
        assert (aseprite_cli.SCRIPTS / name).is_file()
    args = aseprite_cli.script_args("load_version.lua", {"asset": "hero"}, Path("a.aseprite"))
    assert args[:3] == ["a.aseprite", "--script-param", "asset=hero"]
    assert args[-1].endswith("load_version.lua")


def test_missing_binary_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(aseprite_cli.ENV_BINARY, "/nonexistent/aseprite")
    with pytest.raises(aseprite_cli.AsepriteNotFound):
        aseprite_cli.batch_command(["x.aseprite"])


def _pw_path() -> str:
    """The `pw` the Lua helpers shell out to; under `uv run` it is the venv one."""
    pw = shutil.which("pw")
    assert pw is not None
    return pw


needs_aseprite = pytest.mark.skipif(
    aseprite_cli.find_aseprite() is None, reason="no Aseprite binary"
)


def _params(project: Path, asset: str = "sprites/hero") -> dict[str, str]:
    return {"asset": asset, "workspace": str(project), "pw": _pw_path()}


@needs_aseprite
def test_send_to_pixelwright_adds_a_version(project: Path) -> None:
    done = aseprite_cli.run_script("send_to_pixelwright.lua", _params(project),
                                   project.parent / "hero.png")  # fmt: skip
    # Aseprite exits 0 on a swallowed script error, so check what the script printed too.
    assert "pixelwright: sprites/hero v001" in done.stdout
    asset = open_asset(load_project(project), project / "assets" / "sprites" / "hero")
    assert asset.versions() == ["v001"]


@needs_aseprite
def test_load_version_opens_the_latest_version(project: Path) -> None:
    asset = open_asset(load_project(project), project / "assets" / "sprites" / "hero")
    with Image.open(project.parent / "hero.png") as im:
        asset.add_version(im.convert("RGBA"))
    done = aseprite_cli.run_script("load_version.lua", _params(project))
    assert "pixelwright: opened sprites/hero v001" in done.stdout


@needs_aseprite
def test_a_failing_script_exits_non_zero(project: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError) as exc:
        aseprite_cli.run_script("load_version.lua", _params(project, "nosuch/asset"))
    assert "no_asset" in exc.value.stdout
