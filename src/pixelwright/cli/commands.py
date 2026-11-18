"""Project commands: `init`, `check`, `status` and `palette` (the flow commands live in
`flow_commands`, generation in `gen_commands`)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pixelwright import flow
from pixelwright.cli.flow_commands import ASSET, _asset, _project, check_v2, init_v2, status_v2
from pixelwright.cli.registry import Outcome, Param, PwError, command
from pixelwright.core.image import RGBImage
from pixelwright.core.ramps import PRESETS, ramp_palette
from pixelwright.core.snap import snap
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
    "import a palette file, discover one from images, build one from ramps, or list them",
    Param("action", help="what to do", required=True, positional=True,
          choices=("import", "discover", "ramps", "show")),
    Param("file", help="palette file (.gpl or .hex) for import"),
    Param("asset", "list", help="discover: asset paths (their newest inputs)"),
    Param("images", "list", help="discover: image files"),
    Param("colors", "int", help="discover: colours (plus up to 8 accents); ramps: hue "
          "families taken from --asset/--images", default=16),
    Param("per_image", "int", help="discover: each image brings this many colours of its "
          "own instead (a scene set: no scene loses its lights to a bigger one)"),
    Param("keys", "list", help="ramps: key colours as name=rrggbb (added to the preset)"),
    Param("preset", help="ramps: starting key colours (default: adventure, or none with "
          "--asset/--images)", choices=("adventure", "none")),
    Param("steps", "int", help="ramps: shades per key colour", default=5),
    Param("swatch", "bool", help="discover, ramps: also save style/references/palette-<name>.png"),
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
    elif a["action"] == "ramps":
        images, names = _images(root, a)
        preset = a["preset"] or ("none" if images else "adventure")
        keys = dict(PRESETS.get(preset, {}))
        if images:  # one ramp per hue family of the images
            keys |= flow.ramp_keys_from(images, a["colors"])
        for item in a["keys"] or []:
            key, _, hexa = item.partition("=")
            if not hexa:
                raise PwError("invalid", f"--keys wants name=rrggbb, got {item!r}")
            keys[key] = hexa
        if not keys:
            raise PwError("invalid", "palette ramps needs --keys, --images, --asset or a --preset")
        try:
            palette = ramp_palette(keys, a["steps"])
        except ValueError as exc:
            raise PwError("invalid", str(exc)) from exc
        name = a["name"] or "ramps"
    else:
        images, names = _images(root, a)
        if not images:
            raise PwError("invalid", "palette discover needs --asset or --images")
        if a["per_image"]:
            palette = flow.palette_per_image(images, a["per_image"])
        else:
            palette = flow.palette_from(images, a["colors"])
        name = a["name"] or names[0]
    dest = folder / f"{name}.gpl"
    folder.mkdir(parents=True, exist_ok=True)
    write_palette(dest, palette)
    outputs = [str(dest)]
    if a["action"] in ("discover", "ramps") and a["swatch"]:
        swatch = project.root / "style" / "references" / f"palette-{name}.png"
        outputs.append(str(flow.write_swatch(palette, swatch)))
    return Outcome(outputs=outputs, data={"palette": name, "colors": len(palette)},
                   text=f"Palette {name}: {len(palette)} colours")  # fmt: skip


def _images(root: Path, a: dict[str, Any]) -> tuple[list[RGBImage], list[str]]:
    """The images named by --asset (newest input at pixel scale) and --images."""
    images, names = [], []
    for rel in a["asset"] or []:
        asset = _asset(root, rel)
        if not asset.inputs() and asset.latest() is None:
            raise PwError("invalid", f"{asset.rel} has no image to take colours from")
        # the raw input at pixel scale: a version already carries a palette's colours
        images.append(flow.prepare(asset).image if asset.inputs() else _version(asset))
        names.append(asset.name)
    for file in a["images"] or []:
        images.append(snap(_rgb_file(Path(file))).image)
        names.append(Path(file).stem)
    return images, names


def _rgb_file(path: Path) -> RGBImage:
    image = read_png(path)
    return image if isinstance(image, RGBImage) else image.to_rgb_image()


def _version(asset: Any) -> RGBImage:
    return _rgb_file(asset.version_path(asset.latest()))
