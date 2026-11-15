"""A workspace: config, role folders, assets, managed `.gitignore`."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pixelwright.workspace.asset import ASSET_ID, Asset, check_asset_id
from pixelwright.workspace.config import (
    CONFIG_NAME,
    WorkspaceConfig,
    load_config,
    save_config,
)
from pixelwright.workspace.gitignore import write_gitignore
from pixelwright.workspace.style import StyleGuide, load_style, save_style

STYLE_SUBDIRS = ("palettes", "references", "tests")


class Workspace:
    def __init__(self, root: Path, config: WorkspaceConfig) -> None:
        self.root = root
        self.config = config

    @classmethod
    def init(cls, root: Path, config: WorkspaceConfig | None = None) -> Workspace:
        root.mkdir(parents=True, exist_ok=True)
        if (root / CONFIG_NAME).exists():
            raise FileExistsError(f"workspace already initialised: {root / CONFIG_NAME}")
        ws = cls(root, config or WorkspaceConfig())
        save_config(root, ws.config)
        for sub in STYLE_SUBDIRS:
            (ws.path("style") / sub).mkdir(parents=True, exist_ok=True)
        if not (ws.path("style") / "style.yaml").exists():
            save_style(ws.path("style"), StyleGuide())
        for role in ("experiments", "assets", "cache"):
            ws.path(role).mkdir(parents=True, exist_ok=True)
        ws.refresh_gitignore()
        return ws

    @classmethod
    def open(cls, root: Path) -> Workspace:
        return cls(root, load_config(root))

    def path(self, role: str) -> Path:
        return self.config.role_path(self.root, role)

    def assets(self) -> list[str]:
        base = self.path("assets")
        return sorted(p.name for p in base.iterdir() if p.is_dir() and ASSET_ID.fullmatch(p.name))

    def asset(self, asset_id: str) -> Asset:
        path = self.path("assets") / check_asset_id(asset_id)
        if not (path / "asset.yaml").is_file():
            raise FileNotFoundError(f"no such asset: {asset_id}")
        return Asset(path)

    def new_asset(
        self,
        asset_id: str,
        kind: str,
        *,
        canvas: Mapping[str, int] | None = None,
        **fields: Any,
    ) -> Asset:
        path = self.path("assets") / check_asset_id(asset_id)
        fields.setdefault("style_version", self.style().version)
        return Asset.create(path, kind, canvas or self.config.canvas, **fields)

    def style(self) -> StyleGuide:
        return load_style(self.path("style"))

    def stale_assets(self) -> list[tuple[str, int]]:
        """Assets made with an older style version than the current one (to re-check)."""
        current = self.style().version
        stale = []
        for asset_id in self.assets():
            used = int(self.asset(asset_id).spec().get("style_version", 0))
            if used < current:
                stale.append((asset_id, used))
        return stale

    def approved_versions(self) -> list[str]:
        found = []
        for asset_id in self.assets():
            asset = self.asset(asset_id)
            for version in asset.versions():
                if asset.stage(version) == "approved":
                    found.append((asset.versions_dir / version).relative_to(self.root).as_posix())
        return found

    def refresh_gitignore(self) -> None:
        write_gitignore(self.root, self.config, self.approved_versions())
