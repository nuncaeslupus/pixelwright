"""`pw migrate`: turn an M0-M3 workspace into a v2 project, in place.

The old `pixelwright.toml` and `assets/` are kept as `pixelwright.toml.bak` and
`assets.bak/`. Each old asset becomes `assets/<kind>s/<id>`; its versions are copied in
order (v0001 → v001), its issues become notes on the matching version.
"""

from __future__ import annotations

import dataclasses
import re
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from pixelwright.asset import Asset, AssetMeta
from pixelwright.files import read_yaml, write_toml
from pixelwright.issues import IssueLog
from pixelwright.project import PROJECT_FILE, Project, ProjectError, init_project

BAK = ".bak"
IMAGE = "image.png"  # the main file of an old version folder


@dataclass
class MigrateResult:
    project: Project
    assets: dict[str, str] = field(default_factory=dict)  # old id -> new path
    versions: int = 0
    issues: int = 0
    warnings: list[str] = field(default_factory=list)


OLD_VERSION = re.compile(r"v\d{4}")


@dataclass
class OldAsset:
    """Just enough of an M0-M3 asset folder to copy it: `asset.yaml`, `versions/vNNNN/`
    and `masks/masks.yaml` (its issues)."""

    path: Path

    @property
    def id(self) -> str:
        return self.path.name

    @property
    def versions_dir(self) -> Path:
        return self.path / "versions"

    def spec(self) -> dict[str, Any]:
        raw = read_yaml(self.path / "asset.yaml")
        return dict(raw) if isinstance(raw, dict) else {}

    def versions(self) -> list[str]:
        if not self.versions_dir.is_dir():
            return []
        names = [p.name for p in self.versions_dir.iterdir() if OLD_VERSION.fullmatch(p.name)]
        return sorted(names, key=lambda n: int(n[1:]))

    def issues(self) -> list[dict[str, Any]]:
        index = self.path / "masks" / "masks.yaml"
        if not index.is_file():
            return []
        raw = read_yaml(index)
        entries = raw.get("masks") if isinstance(raw, dict) else None
        return [dict(e) for e in entries or [] if isinstance(e, dict)]


def _old_config(root: Path) -> dict[str, Any]:
    """The old `pixelwright.toml` (roles, canvas); refuses a v2 project or no project."""
    file = root / PROJECT_FILE
    if not file.is_file():
        raise ProjectError(f"{root}: no {PROJECT_FILE}, nothing to migrate")
    with file.open("rb") as fh:
        data = tomllib.load(fh)
    if "project" in data:
        raise ProjectError(f"{root}: already a v2 project")
    return data


def _author(old: str) -> str:
    return {"human": "person", "script": "script"}.get(old, "ai")


def _palette_name(ref: object) -> str | None:
    """`style:palettes/scene.gpl` → `scene`."""
    if not isinstance(ref, str) or not ref.endswith(".gpl"):
        return None
    return Path(ref.split(":", 1)[-1]).stem


def migrate(root: Path) -> MigrateResult:
    root = root.resolve()
    old = _old_config(root)
    roles = old.get("roles", {})
    old_assets_dir = root / roles.get("assets", "assets")
    old_style_dir = root / roles.get("style", "style")
    canvas = {"width": 320, "height": 180, **old.get("canvas", {})}
    if old_assets_dir.resolve() == (root / "assets").resolve():
        bak_assets = root / f"assets{BAK}"
        if bak_assets.exists():
            raise ProjectError(f"{bak_assets} exists; move it away first")
        old_assets_dir = old_assets_dir.rename(bak_assets)
    (root / PROJECT_FILE).rename(root / f"{PROJECT_FILE}{BAK}")

    project = init_project(root)
    project = dataclasses.replace(project, canvas=canvas)
    write_toml(root / PROJECT_FILE, project.to_dict())
    result = MigrateResult(project)
    if old_style_dir.resolve() != (root / "style").resolve():
        for gpl in sorted(old_style_dir.rglob("*.gpl")):
            shutil.copy2(gpl, project.palettes_dir / gpl.name)

    for old_dir in sorted(p for p in old_assets_dir.iterdir() if (p / "asset.yaml").is_file()):
        _migrate_asset(project, OldAsset(old_dir), result)
    return result


def _migrate_asset(project: Project, old: OldAsset, result: MigrateResult) -> None:
    spec = old.spec()
    kind = str(spec.get("kind") or "sprite")
    new = Asset.create(project, f"{kind}s/{old.id}", kind=kind)
    palette = _palette_name(spec.get("palette"))
    if palette:
        meta = new.meta()
        new.save_meta(AssetMeta(**{**dataclasses.asdict(meta), "palettes": [palette]}))
    mapping: dict[str, str] = {}
    for version in old.versions():
        image_path = old.versions_dir / version / IMAGE
        if not image_path.is_file():
            result.warnings.append(f"{old.id}/{version}: no {IMAGE}, skipped")
            continue
        with Image.open(image_path) as im:
            mapping[version] = new.add_version(im.convert("RGBA"))
    result.versions += len(mapping)
    if mapping:
        new.set_state("review")
    log = IssueLog(new)
    entries = old.issues()
    if entries and not mapping:
        result.warnings.append(f"{old.id}: {len(entries)} issue(s) dropped (no version)")
        entries = []
    for entry in entries:
        _migrate_issue(log, entry, mapping)
        result.issues += 1
    result.assets[old.id] = new.rel


def _migrate_issue(log: IssueLog, entry: dict[str, Any], mapping: dict[str, str]) -> None:
    message = entry.get("note") or entry.get("rule") or f"migrated issue {entry['id']}"
    areas = [{"box": list(entry["box"])}] if entry.get("box") else []
    issue = log.raise_issue(
        message,
        author=_author(str(entry.get("author", "human"))),
        version=mapping.get(str(entry.get("version"))) or None,
        areas=areas,
        rule=entry.get("rule") or None,
    )
    status = entry.get("status", "open")
    if status == "fixed":
        log.mark_fixed(issue.id, by="person")
    elif status != "open":
        log.reject_issue(issue.id, f"{status} before migration", by="person")
