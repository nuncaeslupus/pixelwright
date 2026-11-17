"""`pw migrate`: turn an M0-M3 workspace into a v2 project, in place.

The old `pixelwright.toml` and `assets/` are kept as `pixelwright.toml.bak` and
`assets.bak/`. Each old asset becomes `assets/<kind>s/<id>`; its versions are copied in
order (v0001 → v001), its issues become notes on the matching version.
"""

from __future__ import annotations

import dataclasses
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from pixelwright.asset import Asset, AssetMeta
from pixelwright.issues import IssueLog
from pixelwright.project import PROJECT_FILE, Project, ProjectError, init_project
from pixelwright.workspace import Workspace
from pixelwright.workspace.asset import Asset as OldAsset
from pixelwright.workspace.files import write_toml

BAK = ".bak"
IMAGE = "image.png"  # the main file of an old version folder


@dataclass
class MigrateResult:
    project: Project
    assets: dict[str, str] = field(default_factory=dict)  # old id -> new path
    versions: int = 0
    issues: int = 0
    warnings: list[str] = field(default_factory=list)


def _author(old: str) -> str:
    return {"human": "person", "script": "script"}.get(old, "ai")


def _palette_name(ref: object) -> str | None:
    """`style:palettes/scene.gpl` → `scene`."""
    if not isinstance(ref, str) or not ref.endswith(".gpl"):
        return None
    return Path(ref.split(":", 1)[-1]).stem


def migrate(root: Path) -> MigrateResult:
    root = root.resolve()
    ws = Workspace.open(root)  # raises when this is not an old workspace
    old_assets_dir = ws.path("assets")
    old_style_dir = ws.path("style")
    canvas = dict(ws.config.canvas)
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
    kind = str(spec["kind"])
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
