"""Asset model v2: one asset is one folder that keeps its whole history.

    <category>/<asset>/
      asset.toml      brief, state, final version, starred versions
      inputs/         what came in (sketches, AI outputs, photos)
      versions/       v001.png v002.png ... never overwritten
      final.png       the finished version

Every file is plain PNG or TOML, readable with no app.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from pixelwright.project import ASSET_FILE, Project, ProjectError, Settings
from pixelwright.workspace.files import write_toml

STATES = ("processing", "review", "finished")
NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
VERSION = re.compile(r"^v(\d{3,})\.png$")
INPUTS = "inputs"
VERSIONS = "versions"
FINAL = "final.png"


class AssetError(ValueError):
    """An asset folder or one of its files is invalid."""


@dataclass
class AssetMeta:
    brief: str = ""
    state: str = "processing"
    final: str | None = None
    starred: list[str] = field(default_factory=list)
    kind: str | None = None
    palettes: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"brief": self.brief, "state": self.state}
        if self.kind:
            data["kind"] = self.kind
        if self.palettes:
            data["palettes"] = list(self.palettes)
        if self.final:
            data["final"] = self.final
        data["starred"] = list(self.starred)
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any], where: Path) -> AssetMeta:
        state = raw.get("state", "processing")
        if state not in STATES:
            raise AssetError(f"{where}: state must be one of {', '.join(STATES)}")
        starred = raw.get("starred", [])
        if not isinstance(starred, list) or not all(isinstance(s, str) for s in starred):
            raise AssetError(f"{where}: starred must be a list of version names")
        palettes = raw.get("palettes")
        if palettes is not None and (
            not isinstance(palettes, list) or not all(isinstance(p, str) for p in palettes)
        ):
            raise AssetError(f"{where}: palettes must be a list of names")
        return cls(
            brief=str(raw.get("brief", "")),
            state=state,
            final=raw.get("final"),
            starred=list(starred),
            kind=raw.get("kind"),
            palettes=palettes,
        )


def version_name(n: int) -> str:
    return f"v{n:03d}"


class Asset:
    def __init__(self, project: Project, path: Path) -> None:
        self.project = project
        self.path = path.resolve()
        if not (self.path / ASSET_FILE).is_file():
            raise AssetError(f"{path}: not an asset (no {ASSET_FILE})")

    # --- creation and lookup -------------------------------------------------

    @classmethod
    def create(
        cls, project: Project, rel: str, *, brief: str = "", kind: str | None = None
    ) -> Asset:
        """Create `assets/<rel>`; every part of `rel` is a lowercase kebab-case name."""
        parts = Path(rel).parts
        if not parts or not all(NAME.fullmatch(p) for p in parts):
            raise AssetError(f"asset path must be kebab-case names like scenes/harbour: {rel!r}")
        path = project.assets_dir / Path(*parts)
        if (path / ASSET_FILE).exists():
            raise AssetError(f"{rel}: asset already exists")
        for sub in (INPUTS, VERSIONS):
            (path / sub).mkdir(parents=True, exist_ok=True)
        write_toml(path / ASSET_FILE, AssetMeta(brief=brief, kind=kind).to_dict())
        return cls(project, path)

    @property
    def rel(self) -> str:
        return self.path.relative_to(self.project.assets_dir.resolve()).as_posix()

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def category(self) -> str | None:
        parts = Path(self.rel).parts
        return parts[0] if len(parts) > 1 else None

    def settings(self) -> Settings:
        return self.project.settings_for(self.path)

    # --- asset.toml ----------------------------------------------------------

    def meta(self) -> AssetMeta:
        file = self.path / ASSET_FILE
        try:
            with file.open("rb") as fh:
                return AssetMeta.from_dict(tomllib.load(fh), file)
        except tomllib.TOMLDecodeError as exc:
            raise AssetError(f"{file}: {exc}") from exc

    def save_meta(self, meta: AssetMeta) -> None:
        write_toml(self.path / ASSET_FILE, meta.to_dict())

    # --- inputs and versions -------------------------------------------------

    def add_input(self, source: Path) -> Path:
        """Copy an image into `inputs/`, never replacing one already there."""
        dest_dir = self.path / INPUTS
        stem, suffix = source.stem, source.suffix.lower()
        dest = dest_dir / f"{stem}{suffix}"
        n = 2
        while dest.exists():
            dest = dest_dir / f"{stem}-{n}{suffix}"
            n += 1
        shutil.copy2(source, dest)
        return dest

    def inputs(self) -> list[Path]:
        return sorted(p for p in (self.path / INPUTS).iterdir() if p.is_file())

    def versions(self) -> list[str]:
        found = []
        for p in (self.path / VERSIONS).iterdir():
            m = VERSION.fullmatch(p.name)
            if m:
                found.append((int(m.group(1)), p.stem))
        return [name for _, name in sorted(found)]

    def latest(self) -> str | None:
        names = self.versions()
        return names[-1] if names else None

    def version_path(self, name: str) -> Path:
        path = self.path / VERSIONS / f"{name}.png"
        if not path.is_file():
            raise AssetError(f"{self.rel}: no version {name}")
        return path

    def add_version(self, image: Image.Image) -> str:
        """Write the next version as PNG; an existing version is never overwritten."""
        versions_dir = self.path / VERSIONS
        while True:
            latest = self.latest()
            n = int(latest[1:]) + 1 if latest else 1
            name = version_name(n)
            fd, tmp = tempfile.mkstemp(dir=versions_dir, prefix=".new.", suffix=".png")
            os.close(fd)
            try:
                image.save(tmp, format="PNG")
                os.link(tmp, versions_dir / f"{name}.png")
            except FileExistsError:
                continue  # another writer took this number; try the next one
            finally:
                Path(tmp).unlink(missing_ok=True)
            meta = self.meta()
            if meta.state == "finished":
                meta.state = "review"
                self.save_meta(meta)
            return name

    def star(self, name: str, on: bool = True) -> None:
        self.version_path(name)
        meta = self.meta()
        if on and name not in meta.starred:
            meta.starred.append(name)
        elif not on and name in meta.starred:
            meta.starred.remove(name)
        self.save_meta(meta)

    def set_state(self, state: str) -> None:
        if state not in STATES:
            raise AssetError(f"state must be one of {', '.join(STATES)}")
        meta = self.meta()
        meta.state = state
        self.save_meta(meta)

    # --- finishing -----------------------------------------------------------

    def export_path(self) -> Path:
        return self.project.export_dir / f"{self.rel}.png"

    def finish(self, name: str | None = None) -> Path:
        """Make a version final: write `final.png`, copy it to the export folder."""
        name = name or self.latest()
        if name is None:
            raise AssetError(f"{self.rel}: no version to finish")
        source = self.version_path(name)
        shutil.copyfile(source, self.path / FINAL)
        target = self.export_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        meta = self.meta()
        meta.final, meta.state = name, "finished"
        self.save_meta(meta)
        if not self.project.keep_all_versions:
            self.prune()
        return target

    def protected(self) -> set[str]:
        """Versions pruning never removes: v001, starred, final and the latest (which
        also keeps version numbers from being reused)."""
        meta = self.meta()
        keep = {version_name(1), *meta.starred}
        if meta.final:
            keep.add(meta.final)
        latest = self.latest()
        if latest:
            keep.add(latest)
        return keep

    def prune(self) -> list[str]:
        """Delete unprotected versions; inputs are never touched. Returns what was removed."""
        keep = self.protected()
        removed = [v for v in self.versions() if v not in keep]
        for name in removed:
            (self.path / VERSIONS / f"{name}.png").unlink()
        return removed


def open_asset(project: Project, path: Path) -> Asset:
    try:
        path.resolve().relative_to(project.assets_dir.resolve())
    except ValueError as exc:
        raise ProjectError(f"{path}: not under {project.assets_dir}") from exc
    return Asset(project, path)


def list_assets(project: Project) -> list[Asset]:
    """Every folder under `assets/` that holds an `asset.toml`."""
    if not project.assets_dir.is_dir():
        return []
    return [Asset(project, f.parent) for f in sorted(project.assets_dir.rglob(ASSET_FILE))]
