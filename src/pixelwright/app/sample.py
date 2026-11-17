"""The sample project opened on first launch: a hillside house at dusk, drawn by code.

Two assets show the flow at once: a pencil sketch and an AI-style painting of the same
scene, both already cleaned by the scripts, so each card shows a real next step.
"""

from __future__ import annotations

import dataclasses
import os
import sys
import tempfile
from pathlib import Path

from pixelwright import flow
from pixelwright.fixtures import tour as drawing
from pixelwright.io.palette_io import write_palette
from pixelwright.io.png import encode_png
from pixelwright.project import PROJECT_FILE, Project, init_project, load_project
from pixelwright.workspace.files import write_toml

NAME = "sample"


def data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "pixelwright"


def create_sample(root: Path | None = None) -> Project:
    """Make the sample project (or return the existing one) and let the scripts run."""
    root = root or data_dir() / NAME
    if (root / PROJECT_FILE).is_file():
        return load_project(root)
    project = init_project(root, name=NAME)
    canvas = {"width": drawing.WIDTH, "height": drawing.HEIGHT}
    project = dataclasses.replace(project, canvas=canvas)
    write_toml(root / PROJECT_FILE, project.to_dict())
    write_palette(project.palettes_dir / "main.gpl", drawing.palette())
    with tempfile.TemporaryDirectory() as tmp:
        for name, image in (("house-sketch", drawing.sketch()), ("house", drawing.painted())):
            src = Path(tmp) / f"{name}.png"
            src.write_bytes(encode_png(image))
            flow.ingest(project, src, "scenes")
    return project
