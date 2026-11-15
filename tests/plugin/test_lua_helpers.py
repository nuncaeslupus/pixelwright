import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from pixelwright.cli import main
from pixelwright.core.image import RGBImage
from pixelwright.io import aseprite_cli
from pixelwright.io.png import write_png
from pixelwright.workspace import Workspace


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = Workspace.init(tmp_path / "ws")
    ws.new_asset("hero", "sprite")
    rgba = np.zeros((8, 8, 4), np.uint8)
    rgba[2:6, 2:6] = (200, 40, 40, 255)
    write_png(tmp_path / "hero.png", RGBImage(rgba))
    return ws.root


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


def test_attach_records_parent_and_note(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    w = ["--workspace", str(workspace)]
    src = str(workspace.parent / "hero.png")
    assert main(["attach", "hero", src, *w]) == 0
    assert main(["attach", "hero", src, "--parent", "v0001", "--note", "hands", *w, "--json"]) == 0
    env = json.loads(capsys.readouterr().out.splitlines()[-1])
    asset = Workspace.open(workspace).asset("hero")
    assert asset.meta(env["version"])["parent"] == "v0001"
    notes = [h for h in asset.history() if h["event"] == "note"]
    assert notes[-1]["note"] == "hands" and notes[-1]["version"] == env["version"]


def _pw_path() -> str:
    """The `pw` the Lua helpers shell out to; under `uv run` it is the venv one."""
    pw = shutil.which("pw")
    assert pw is not None
    return pw


needs_aseprite = pytest.mark.skipif(
    aseprite_cli.find_aseprite() is None, reason="no Aseprite binary"
)


@needs_aseprite
def test_send_to_pixelwright_creates_draft_and_note(workspace: Path) -> None:
    params = {"asset": "hero", "note": "retouched", "workspace": str(workspace), "pw": _pw_path()}
    done = aseprite_cli.run_script("send_to_pixelwright.lua", params, workspace.parent / "hero.png")
    # Aseprite exits 0 on a swallowed script error, so check what the script printed too.
    assert "pixelwright: hero v0001" in done.stdout
    asset = Workspace.open(workspace).asset("hero")
    assert asset.versions() == ["v0001"]
    assert any(h["event"] == "note" and h["note"] == "retouched" for h in asset.history())


@needs_aseprite
def test_load_version_opens_the_latest_version(workspace: Path) -> None:
    src = str(workspace.parent / "hero.png")
    assert main(["attach", "hero", src, "--workspace", str(workspace)]) == 0
    params = {"asset": "hero", "workspace": str(workspace), "pw": _pw_path()}
    done = aseprite_cli.run_script("load_version.lua", params)
    assert "pixelwright: opened hero v0001" in done.stdout


@needs_aseprite
def test_a_failing_script_exits_non_zero(workspace: Path) -> None:
    params = {"asset": "nosuch", "workspace": str(workspace), "pw": _pw_path()}
    with pytest.raises(subprocess.CalledProcessError) as exc:
        aseprite_cli.run_script("load_version.lua", params)
    assert "not_found" in exc.value.stdout
