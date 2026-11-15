"""Style guide (`style/style.yaml` @1): versioned conventions every asset records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pixelwright.core.palette import Palette, Ramps
from pixelwright.workspace import schema
from pixelwright.workspace.asset import utc_now
from pixelwright.workspace.files import append_jsonl, read_yaml, write_yaml

STYLE_FILE = "style.yaml"
HISTORY_FILE = "history.jsonl"
ARCHIVE_DIR = "versions"


@dataclass
class StyleGuide:
    version: int = 1
    palettes: list[str] = field(default_factory=list)  # files under style/, e.g. palettes/a.gpl
    ramps: str = ""  # e.g. palettes/ramps.yaml
    light: dict[str, Any] = field(default_factory=dict)
    outline: dict[str, Any] = field(default_factory=dict)
    density: dict[str, Any] = field(default_factory=dict)
    dithering: dict[str, Any] = field(default_factory=lambda: {"allowed": False})
    references: list[str] = field(default_factory=list)
    presets: dict[str, Any] = field(default_factory=dict)
    test_assets: list[str] = field(default_factory=list)  # asset ids `style test` checks
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return schema.stamp("style", asdict(self))

    @classmethod
    def from_dict(cls, raw: object) -> StyleGuide:
        data = dict(schema.validate("style", raw))
        data.pop("schema")
        known = set(cls.__dataclass_fields__)
        unknown = set(data) - known
        if unknown:
            raise schema.SchemaError(f"style: unknown keys {sorted(unknown)}")
        guide = cls(**data)
        if guide.version < 1:
            raise schema.SchemaError("style: version must be >= 1")
        return guide


def style_path(style_dir: Path) -> Path:
    return style_dir / STYLE_FILE


def load_style(style_dir: Path) -> StyleGuide:
    return StyleGuide.from_dict(read_yaml(style_path(style_dir)))


def save_style(style_dir: Path, guide: StyleGuide) -> None:
    write_yaml(style_path(style_dir), guide.to_dict())


def bump_style(
    style_dir: Path, changes: Mapping[str, Any], *, note: str = "", author: str = "human"
) -> StyleGuide:
    """Apply `changes`, raise the version by one, archive the old guide and log the bump."""
    old = load_style(style_dir)
    if "version" in changes:
        raise ValueError("the version is raised by the bump itself")
    archive = style_dir / ARCHIVE_DIR / f"style-v{old.version:04d}.yaml"
    write_yaml(archive, old.to_dict())
    new = StyleGuide.from_dict({**old.to_dict(), **changes, "version": old.version + 1})
    save_style(style_dir, new)
    record = {"event": "style_bump", "time": utc_now(), "from": old.version, "to": new.version}
    append_jsonl(
        style_dir / HISTORY_FILE,
        schema.stamp(
            "history", {**record, "changed": sorted(changes), "note": note, "author": author}
        ),
    )
    return new


def load_palettes(style_dir: Path, guide: StyleGuide) -> dict[str, Palette]:
    from pixelwright.io.palette_io import read_palette

    return {rel: read_palette(style_dir / rel) for rel in guide.palettes}


def load_ramps(style_dir: Path, guide: StyleGuide) -> Ramps | None:
    from pixelwright.io.palette_io import read_ramps

    return read_ramps(style_dir / guide.ramps) if guide.ramps else None
