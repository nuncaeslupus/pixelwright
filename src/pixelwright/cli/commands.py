"""Project commands: `init`, `check`, `status` and `palette` (the flow commands live in
`flow_commands`, generation in `gen_commands`)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pixelwright.cli.flow_commands import ASSET, _asset, _project, check_v2, init_v2, status_v2
from pixelwright.cli.registry import Outcome, Param, PwError, command
from pixelwright.core.image import RGBImage
from pixelwright.core.quantize import discover_palette
from pixelwright.io.palette_io import read_palette, write_palette
from pixelwright.io.png import read_png


@command(
    "init",
    "create a project (pixelwright.toml, assets/, style/palettes/, AGENTS.md)",
    Param("path", help="project folder (same as --workspace)", positional=True),
    needs_workspace=False,
)
def cmd_init(root: Path, a: dict[str, Any]) -> Outcome:
    return init_v2(Path(a["path"]) if a["path"] else root, a)


@command(
    "check",
    "run the pixel checks on a version and raise an issue for each problem",
    ASSET,
    Param("version", help="version, e.g. v003 (default: the latest)"),
)
def cmd_check(root: Path, a: dict[str, Any]) -> Outcome:
    out: Outcome = check_v2(root, a)
    return out


@command(
    "status",
    "every asset (or one) with its state and next step",
    Param("asset", help="asset path, e.g. scenes/harbour (default: every asset)", positional=True),
)
def cmd_status(root: Path, a: dict[str, Any]) -> Outcome:
    return status_v2(root, a)


@command(
    "palette",
    "import a palette file, discover one from an asset's latest version, or list them",
    Param("action", help="what to do", required=True, positional=True,
          choices=("import", "discover", "show")),
    Param("file", help="palette file (.gpl or .hex) for import"),
    Param("asset", help="asset path for discover"),
    Param("colors", "int", help="number of colors for discover", default=16),
    Param("name", help="palette name (default: from the file or the asset)"),
)  # fmt: skip
def cmd_palette(root: Path, a: dict[str, Any]) -> Outcome:
    project = _project(root)
    folder = project.palettes_dir
    if a["action"] == "show":
        names = project.palette_names()
        sizes = {name: len(read_palette(folder / f"{name}.gpl")) for name in names}
        text = "\n".join(f"{k}  {v}" for k, v in sizes.items())
        return Outcome(data={"palettes": sizes}, text=text)
    if a["action"] == "import":
        if not a["file"]:
            raise PwError("invalid", "palette import needs --file")
        src = Path(a["file"])
        palette, name = read_palette(src), a["name"] or src.stem
    else:
        asset = _asset(root, a["asset"])
        latest = asset.latest()
        if latest is None:
            raise PwError("invalid", f"{asset.rel} has no version to take colours from")
        image = read_png(asset.version_path(latest))
        rgb = image if isinstance(image, RGBImage) else image.to_rgb_image()
        palette, name = discover_palette(rgb, a["colors"]), a["name"] or asset.name
    dest = folder / f"{name}.gpl"
    folder.mkdir(parents=True, exist_ok=True)
    write_palette(dest, palette)
    return Outcome(outputs=[str(dest)], data={"palette": name, "colors": len(palette)},
                   text=f"Palette {name}: {len(palette)} colours")  # fmt: skip
