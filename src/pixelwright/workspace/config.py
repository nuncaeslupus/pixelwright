"""`pixelwright.toml`: workspace roles to paths, canvas defaults, stages to commit."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pixelwright.workspace import schema
from pixelwright.workspace.files import write_toml

CONFIG_NAME = "pixelwright.toml"

STAGES = ("experiment", "draft", "approved", "final")

DEFAULT_ROLES: dict[str, str] = {
    "style": "style",
    "assets": "assets",
    "experiments": "experiments",
    "cache": "cache",
}
DEFAULT_CANVAS: dict[str, int] = {"width": 320, "height": 180}
DEFAULT_COMMIT: tuple[str, ...] = ("approved", "final")


@dataclass
class WorkspaceConfig:
    roles: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ROLES))
    canvas: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_CANVAS))
    commit: list[str] = field(default_factory=lambda: list(DEFAULT_COMMIT))
    # Per asset kind, where final exports go (relative to the workspace root),
    # e.g. {"background": "game/art/backgrounds"}.
    exports: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unknown = set(self.commit) - set(STAGES)
        if unknown:
            raise schema.SchemaError(f"workspace: unknown stages in commit: {sorted(unknown)}")
        for role, rel in {**self.roles, **self.exports}.items():
            if Path(rel).is_absolute() or ".." in Path(rel).parts:
                raise schema.SchemaError(f"workspace: path for {role!r} must stay inside: {rel}")

    def role_path(self, root: Path, role: str) -> Path:
        return root / self.roles.get(role, DEFAULT_ROLES[role])

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "roles": self.roles,
            "canvas": self.canvas,
            "commit": self.commit,
            "exports": self.exports,
        }
        data.update(self.extra)
        return schema.stamp("workspace", data)

    @classmethod
    def from_dict(cls, raw: object) -> WorkspaceConfig:
        data = dict(schema.validate("workspace", raw))
        data.pop("schema")
        known = {"roles", "canvas", "commit", "exports"}
        return cls(
            roles={**DEFAULT_ROLES, **data["roles"]},
            canvas={**DEFAULT_CANVAS, **data["canvas"]},
            commit=list(data["commit"]),
            exports=dict(data.get("exports", {})),
            extra={k: v for k, v in data.items() if k not in known},
        )


def load_config(root: Path) -> WorkspaceConfig:
    with (root / CONFIG_NAME).open("rb") as fh:
        return WorkspaceConfig.from_dict(tomllib.load(fh))


def save_config(root: Path, config: WorkspaceConfig) -> None:
    write_toml(root / CONFIG_NAME, config.to_dict())
