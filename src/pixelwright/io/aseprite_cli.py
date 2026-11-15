"""Headless Aseprite: find the binary, export files, run the Lua helpers in batch mode."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

ENV_BINARY = "PW_ASEPRITE"
SCRIPTS = Path(__file__).resolve().parents[3] / "plugin" / "aseprite" / "scripts"


class AsepriteNotFound(FileNotFoundError):
    pass


def find_aseprite() -> Path | None:
    """`$PW_ASEPRITE`, else `aseprite` on PATH."""
    configured = os.environ.get(ENV_BINARY)
    found = configured or shutil.which("aseprite")
    return Path(found) if found and Path(found).is_file() else None


def batch_command(args: Sequence[str], binary: Path | None = None) -> list[str]:
    exe = binary or find_aseprite()
    if exe is None:
        raise AsepriteNotFound(f"Aseprite not found: set {ENV_BINARY} or put it on PATH")
    return [str(exe), "--batch", *args]


def run_batch(
    args: Sequence[str], binary: Path | None = None, timeout: float = 120.0
) -> subprocess.CompletedProcess[str]:
    cmd = batch_command(args, binary)
    return subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout)


def export(src: Path, dest: Path, binary: Path | None = None) -> Path:
    """Save `src` (any format Aseprite opens) as `dest`; the suffix picks the format."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_batch([str(src), "--save-as", str(dest)], binary)
    return dest


def script_args(script: str, params: Mapping[str, str], sprite: Path | None = None) -> list[str]:
    args = [str(sprite)] if sprite else []
    for key, value in params.items():
        args += ["--script-param", f"{key}={value}"]
    return [*args, "--script", str(SCRIPTS / script)]


def run_script(
    script: str,
    params: Mapping[str, str],
    sprite: Path | None = None,
    binary: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one of `plugin/aseprite/scripts/*.lua` headless, optionally on an open sprite."""
    return run_batch(script_args(script, params, sprite), binary)
