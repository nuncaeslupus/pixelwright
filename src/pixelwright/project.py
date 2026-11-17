"""Project model v2: a project is a folder with `pixelwright.toml`.

Settings resolve by nearest folder: the asset's `asset.toml`, then each parent
category's `category.toml`, then the project file. Everything stays plain TOML.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pixelwright.workspace.files import write_toml

PROJECT_FILE = "pixelwright.toml"
CATEGORY_FILE = "category.toml"
ASSET_FILE = "asset.toml"
ASSETS_DIR = "assets"
PALETTES_DIR = Path("style") / "palettes"

DEFAULT_CANVAS: dict[str, int] = {"width": 320, "height": 180}
DEFAULT_PALETTE = "main"
RULE_LEVELS = ("error", "warn", "off")


class ProjectError(ValueError):
    """A project file is missing or malformed."""


@dataclass(frozen=True)
class Settings:
    """What applies to one asset (or category) after nearest-folder resolution."""

    palettes: tuple[str, ...]
    canvas: dict[str, int]
    kind: str | None = None
    checks: dict[str, str] = field(default_factory=dict)

    @property
    def palette(self) -> str:
        return self.palettes[0]


@dataclass(frozen=True)
class Project:
    root: Path
    name: str
    keep_all_versions: bool = True
    export: str = "export"
    canvas: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_CANVAS))
    default_palette: str = DEFAULT_PALETTE
    rules: dict[str, str] = field(default_factory=dict)

    @property
    def assets_dir(self) -> Path:
        return self.root / ASSETS_DIR

    @property
    def palettes_dir(self) -> Path:
        return self.root / PALETTES_DIR

    @property
    def export_dir(self) -> Path:
        path = Path(self.export).expanduser()
        return path if path.is_absolute() else (self.root / path).resolve()

    def palette_names(self) -> list[str]:
        return sorted(p.stem for p in self.palettes_dir.glob("*.gpl"))

    def categories(self) -> list[str]:
        """Top-level folders under `assets/` (the left panel of the app)."""
        if not self.assets_dir.is_dir():
            return []
        return sorted(p.name for p in self.assets_dir.iterdir() if p.is_dir())

    def settings_for(self, folder: Path) -> Settings:
        return resolve_settings(self, folder)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "project": {
                "name": self.name,
                "keep_all_versions": self.keep_all_versions,
                "export": self.export,
            },
            "canvas": dict(self.canvas),
            "palettes": {"default": self.default_palette},
        }
        if self.rules:
            data["rules"] = dict(self.rules)
        return data


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ProjectError(f"{path}: {exc}") from exc


def _canvas(raw: object, where: Path) -> dict[str, int]:
    if not isinstance(raw, dict) or not all(
        k in ("width", "height") and isinstance(v, int) and not isinstance(v, bool) and v > 0
        for k, v in raw.items()
    ):
        raise ProjectError(f"{where}: [canvas] takes positive integers width and height")
    return dict(raw)


def _checks(raw: object, where: Path, key: str) -> dict[str, str]:
    if not isinstance(raw, dict) or not all(
        isinstance(k, str) and v in RULE_LEVELS for k, v in raw.items()
    ):
        raise ProjectError(f"{where}: [{key}] maps rule ids to one of {', '.join(RULE_LEVELS)}")
    return dict(raw)


def _str(raw: object, where: Path, key: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise ProjectError(f"{where}: {key} must be a non-empty string")
    return raw


def find_project(path: Path) -> Path:
    """The project root containing `path` (a file or folder inside it)."""
    start = path.resolve()
    for candidate in (start, *start.parents):
        if (candidate / PROJECT_FILE).is_file():
            return candidate
    raise ProjectError(f"no {PROJECT_FILE} in {start} or any parent folder")


def load_project(root: Path) -> Project:
    file = root / PROJECT_FILE
    if not file.is_file():
        raise ProjectError(f"{root}: not a project (no {PROJECT_FILE})")
    data = _read_toml(file)
    meta = data.get("project", {})
    if not isinstance(meta, dict):
        raise ProjectError(f"{file}: [project] must be a table")
    keep = meta.get("keep_all_versions", True)
    if not isinstance(keep, bool):
        raise ProjectError(f"{file}: keep_all_versions must be true or false")
    palettes = data.get("palettes", {})
    if not isinstance(palettes, dict):
        raise ProjectError(f"{file}: [palettes] must be a table")
    return Project(
        root=root.resolve(),
        name=_str(meta.get("name", root.resolve().name), file, "name"),
        keep_all_versions=keep,
        export=_str(meta.get("export", "export"), file, "export"),
        canvas={**DEFAULT_CANVAS, **_canvas(data.get("canvas", {}), file)},
        default_palette=_str(palettes.get("default", DEFAULT_PALETTE), file, "palettes.default"),
        rules=_checks(data.get("rules", {}), file, "rules"),
    )


def init_project(root: Path, name: str | None = None) -> Project:
    """Create a project folder; refuses to overwrite an existing project file."""
    if (root / PROJECT_FILE).exists():
        raise ProjectError(f"{root}: already a project")
    root.mkdir(parents=True, exist_ok=True)
    project = Project(root=root.resolve(), name=name or root.resolve().name)
    for sub in (ASSETS_DIR, str(PALETTES_DIR)):
        (root / sub).mkdir(parents=True, exist_ok=True)
    write_toml(root / PROJECT_FILE, project.to_dict())
    return project


def resolve_settings(project: Project, folder: Path) -> Settings:
    """Merge project defaults with each `category.toml` / `asset.toml` down to `folder`."""
    target = folder.resolve()
    try:
        rel = target.relative_to(project.assets_dir.resolve())
    except ValueError as exc:
        raise ProjectError(f"{folder}: not under {project.assets_dir}") from exc

    palettes: tuple[str, ...] = (project.default_palette,)
    canvas = dict(project.canvas)
    checks = dict(project.rules)
    kind: str | None = None

    current = project.assets_dir.resolve()
    for part in ("", *rel.parts):
        current = current / part if part else current
        for name in (CATEGORY_FILE, ASSET_FILE):
            file = current / name
            if not file.is_file():
                continue
            layer = _read_toml(file)
            if "palettes" in layer:
                raw = layer["palettes"]
                if not isinstance(raw, list) or not raw:
                    raise ProjectError(f"{file}: palettes must be a non-empty list of names")
                palettes = tuple(_str(p, file, "palettes") for p in raw)
            elif "palette" in layer:
                palettes = (_str(layer["palette"], file, "palette"),)
            if "canvas" in layer:
                canvas.update(_canvas(layer["canvas"], file))
            if "checks" in layer:
                checks.update(_checks(layer["checks"], file, "checks"))
            if "kind" in layer:
                kind = _str(layer["kind"], file, "kind")
    return Settings(palettes=palettes, canvas=canvas, kind=kind, checks=checks)
