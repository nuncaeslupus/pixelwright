"""Flow commands on the v2 project model (spec §5 CLI table).

`init`, `check` and `status` keep their names: on a v2 project (a `pixelwright.toml`
with a `[project]` table) the old handlers hand over to the functions here.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from PIL import Image as PILImage

from pixelwright import flow, generate
from pixelwright.asset import Asset, AssetError, list_assets, open_asset
from pixelwright.cli.registry import Outcome, Param, PwError, command
from pixelwright.core.providers import ProviderError
from pixelwright.issues import KINDS, IssueError, IssueLog
from pixelwright.migrate import migrate
from pixelwright.project import PROJECT_FILE, Project, ProjectError, init_project, load_project

ASSET = Param("asset", help="asset path under assets/, e.g. scenes/harbour", positional=True)


def is_v2(root: Path) -> bool:
    try:
        with (root / PROJECT_FILE).open("rb") as fh:
            return "project" in tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return False


def _project(root: Path) -> Project:
    try:
        return load_project(root)
    except ProjectError as exc:
        raise PwError("no_project", str(exc)) from exc


def _asset(root: Path, rel: str | None) -> Asset:
    if not rel:
        raise PwError("usage", "name the asset, e.g. scenes/harbour", exit_code=2)
    project = _project(root)
    try:
        return open_asset(project, project.assets_dir / rel)
    except (AssetError, ProjectError) as exc:
        raise PwError("no_asset", str(exc)) from exc


def _guard(fn: Any) -> Any:
    """Report model errors in the envelope instead of as tracebacks."""

    def wrapped(root: Path, a: dict[str, Any]) -> Outcome:
        try:
            out: Outcome = fn(root, a)
            return out
        except (AssetError, IssueError, ProjectError, ValueError) as exc:
            if isinstance(exc, (PwError, ProviderError)):
                raise
            raise PwError("invalid", str(exc)) from exc

    wrapped.__name__ = fn.__name__
    wrapped.__doc__ = fn.__doc__
    return wrapped


# --- handed over from the old command names ------------------------------------------


def init_v2(root: Path, a: dict[str, Any]) -> Outcome:
    try:
        project = init_project(root)
    except ProjectError as exc:
        raise PwError("exists", str(exc)) from exc
    return Outcome(
        outputs=[str(project.root / PROJECT_FILE)],
        text=f"Created project {project.name}. Next: pw add <category>/<name> --from <image>",
    )


@_guard
def check_v2(root: Path, a: dict[str, Any]) -> Outcome:
    asset = _asset(root, a["asset"])
    results, issues = flow.run_checks(asset, a.get("version"))
    version = a.get("version") or asset.latest()
    flagged = [r.to_dict() for r in results if r.flagged]
    return Outcome(
        asset.rel,
        version,
        data={"results": [r.to_dict() for r in results], "raised": [i.id for i in issues]},
        text=f"{len(flagged)} check(s) flagged, {len(issues)} new issue(s) on {version}",
    )


def status_v2(root: Path, a: dict[str, Any]) -> Outcome:
    project = _project(root)
    assets = [_asset(root, a["asset"])] if a.get("asset") else list_assets(project)
    rows = flow.status(assets)
    text = "\n".join(f"{r['asset']}  {r['state']}  → {r['next']['text']}" for r in rows)
    return Outcome(a.get("asset"), data={"assets": rows}, text=text or "No assets yet.")


# --- new commands --------------------------------------------------------------------


@command(
    "add",
    "create an asset from an image (copied into its inputs/), or add another input",
    ASSET,
    Param("from", help="image file", required=True),
    Param("brief", help="what the asset should be", default=""),
    Param("kind", help="asset kind (default: from the category)"),
)
@_guard
def cmd_add(root: Path, a: dict[str, Any]) -> Outcome:
    project = _project(root)
    source = Path(a["from"])
    if not source.is_file():
        raise PwError("no_file", f"no such image: {source}")
    path = project.assets_dir / a["asset"]
    if (path / "asset.toml").is_file():
        asset = open_asset(project, path)
    else:
        asset = Asset.create(project, a["asset"], brief=a["brief"], kind=a["kind"])
    added = asset.add_input(source)
    return Outcome(asset.rel, outputs=[str(added)], text=f"Added {added.name} to {asset.rel}")


@command(
    "normalize",
    "clean an input into the next version: pixel grid, palette, stray pixels",
    ASSET,
    Param("input", help="input file (default: the newest in inputs/)"),
)
@_guard
def cmd_normalize(root: Path, a: dict[str, Any]) -> Outcome:
    asset = _asset(root, a["asset"])
    res = flow.normalize(asset, Path(a["input"]) if a["input"] else None)
    return Outcome(
        asset.rel,
        res.version,
        outputs=[str(asset.version_path(res.version))],
        data={"scale": res.scale, "size": list(res.size), "palette": res.palette},
        warnings=res.warnings,
        text=f"{asset.rel}: {res.version} ({res.size[0]}x{res.size[1]}, palette {res.palette})",
    )


@command(
    "issues",
    "list, raise, reply to, reject or mark fixed the issues of an asset",
    ASSET,
    Param("action", default="list", positional=True,
          choices=("list", "raise", "reply", "reject", "mark-fixed")),
    Param("id", help="issue id (reply, reject, mark-fixed)"),
    Param("message", help="text of the issue, reply or rejection reason", default=""),
    Param("by", help="who acts", default="person", choices=("person", "ai", "script")),
    Param("kind", help="issue kind (raise)", default="note", choices=KINDS),
    Param("target", help="'ai' makes the issue a request for the AI", choices=("ai",)),
    Param("box", "list", help="areas as x,y,w,h (raise)"),
    Param("promote", "bool", help="reject: make the reason a style rule"),
    Param("scope", help="reject --promote: where the rule applies", default="asset",
          choices=("asset", "category", "project")),
    Param("state", help="list filter", default="open",
          choices=("open", "fixed", "rejected", "all")),
)  # fmt: skip
@_guard
def cmd_issues(root: Path, a: dict[str, Any]) -> Outcome:
    asset = _asset(root, a["asset"])
    log = IssueLog(asset)
    action = a["action"]
    if action == "list":
        found = [i.__dict__ for i in log.state().issues.values() if a["state"] in ("all", i.state)]
        return Outcome(asset.rel, data={"issues": found}, text=f"{len(found)} issue(s)")
    if action == "raise":
        if not a["message"]:
            raise PwError("usage", "--message is required", exit_code=2)
        areas = [{"box": [int(v) for v in b.split(",")]} for b in a["box"] or []]
        issue = log.raise_issue(
            a["message"], author=a["by"], kind=a["kind"], target=a["target"], areas=areas
        )
        return Outcome(asset.rel, issue.version, data={"issue": issue.__dict__}, text=issue.id)
    if not a["id"]:
        raise PwError("usage", f"{action} needs --id", exit_code=2)
    if action == "reply":
        log.reply(a["id"], a["message"], by=a["by"])
    elif action == "reject":
        log.reject_issue(a["id"], a["message"], by=a["by"], promote=a["promote"], scope=a["scope"])
    else:
        log.mark_fixed(a["id"], by=a["by"])
    return Outcome(asset.rel, data={"issue": log.issue(a["id"]).__dict__}, text=f"{action}: done")


@command(
    "fix",
    "propose a fix image, or accept or reject fixes (accepting several makes one version)",
    ASSET,
    Param("action", positional=True, required=True, choices=("propose", "accept", "reject")),
    Param("ids", "list", help="fix ids (accept, reject) or the issue id (propose)"),
    Param("file", help="candidate image (propose)"),
    Param("by", help="who acts", default="person", choices=("person", "ai", "script")),
    Param("reason", help="why (reject)", default=""),
)
@_guard
def cmd_fix(root: Path, a: dict[str, Any]) -> Outcome:
    asset = _asset(root, a["asset"])
    log = IssueLog(asset)
    ids = a["ids"] or []
    if not ids:
        raise PwError("usage", "--ids is required", exit_code=2)
    if a["action"] == "propose":
        if not a["file"]:
            raise PwError("usage", "propose needs --file", exit_code=2)
        with PILImage.open(a["file"]) as im:
            fix = log.propose_fix(ids[0], im.convert("RGBA"), by=a["by"])
        return Outcome(
            asset.rel, outputs=[str(asset.path / fix.image)], data={"fix": fix.id}, text=fix.id
        )
    if a["action"] == "accept":
        version = log.accept(ids, by=a["by"])
        return Outcome(asset.rel, version, text=f"Accepted → {version}")
    for fid in ids:
        log.reject_fix(fid, a["reason"], by=a["by"])
    return Outcome(asset.rel, text=f"Rejected {len(ids)} fix(es)")


@command("undo", "undo the last accepted fixes (writes the previous image as a new version)", ASSET)
@_guard
def cmd_undo(root: Path, a: dict[str, Any]) -> Outcome:
    asset = _asset(root, a["asset"])
    version = IssueLog(asset).undo()
    return Outcome(asset.rel, version, text=f"Undone → {version}")


@command("redo", "redo the last undone fixes", ASSET)
@_guard
def cmd_redo(root: Path, a: dict[str, Any]) -> Outcome:
    asset = _asset(root, a["asset"])
    version = IssueLog(asset).redo()
    return Outcome(asset.rel, version, text=f"Redone → {version}")


@command(
    "star",
    "keep a version even when old versions are pruned",
    ASSET,
    Param("version", help="version, e.g. v003", required=True, positional=True),
    Param("off", "bool", help="remove the star"),
)
@_guard
def cmd_star(root: Path, a: dict[str, Any]) -> Outcome:
    asset = _asset(root, a["asset"])
    asset.star(a["version"], on=not a["off"])
    return Outcome(asset.rel, a["version"], data={"starred": asset.meta().starred})


@command(
    "finish",
    "make a version final: write final.png and copy it to the export folder",
    ASSET,
    Param("version", help="version (default: the latest)", positional=True),
)
@_guard
def cmd_finish(root: Path, a: dict[str, Any]) -> Outcome:
    asset = _asset(root, a["asset"])
    target = asset.finish(a["version"])
    final = asset.meta().final
    return Outcome(
        asset.rel, final, outputs=[str(target)], text=f"Finished with {final} → {target}"
    )


@command(
    "migrate",
    "turn an M0-M3 workspace into a v2 project (old files kept as .bak)",
)
@_guard
def cmd_migrate(root: Path, a: dict[str, Any]) -> Outcome:
    if is_v2(root):
        raise PwError("exists", f"{root}: already a v2 project")
    res = migrate(root)
    return Outcome(
        outputs=[str(res.project.root / PROJECT_FILE)],
        data={"assets": res.assets, "versions": res.versions, "issues": res.issues},
        warnings=res.warnings,
        text=f"Migrated {len(res.assets)} asset(s), {res.versions} version(s), "
        f"{res.issues} issue(s). Old files: pixelwright.toml.bak, assets.bak/",
    )


@_guard
def generate_v2(root: Path, a: dict[str, Any]) -> Outcome:
    """`pw generate` on a v2 project: images become inputs, then normalised versions."""
    asset = _asset(root, a["asset"])
    prompt = Path(a["prompt_file"]).read_text(encoding="utf-8") if a["prompt_file"] else a["prompt"]
    if a.get("issue"):
        res = generate.repaint(
            asset, a["issue"], prompt, provider=a["provider"], seed=a["seed"],
            budget_override=a["budget_override"],
        )  # fmt: skip
    else:
        size = None
        if a["size"]:
            w, _, h = a["size"].lower().partition("x")
            size = (int(w), int(h))
        res = generate.generate(
            asset, prompt, provider=a["provider"], mode=a["mode"], init=a["init"],
            n=a["n"], seed=a["seed"], size=size, dry_run=a["dry_run"],
            budget_override=a["budget_override"],
        )  # fmt: skip
    data = {k: v for k, v in res.__dict__.items() if k not in ("inputs", "warnings")}
    data["inputs"] = [str(p) for p in res.inputs]
    outputs = [str(asset.version_path(v)) for v in res.versions]
    if res.fix:
        outputs = [str(asset.path / IssueLog(asset).state().fixes[res.fix].image)]
    text = (
        f"{asset.rel}: fix {res.fix} proposed for {a['issue']}"
        if res.fix
        else f"{asset.rel}: {', '.join(res.versions) or 'dry run'} ({res.provider}, {res.mode})"
    )
    version = res.versions[-1] if res.versions else None
    return Outcome(asset.rel, version, outputs=outputs, data=data, warnings=res.warnings, text=text)
