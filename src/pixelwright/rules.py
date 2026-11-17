"""Style rules learnt from rejections, kept in `style/rules.toml`.

Rejecting an issue with "promote" records its reason as a rule for a scope (the
asset, its category, or the whole project); checks then stop raising that rule there.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pixelwright.files import write_toml

if TYPE_CHECKING:
    from pixelwright.asset import Asset
    from pixelwright.core.checks import CheckResult
    from pixelwright.issues import Issue, IssueLog
    from pixelwright.project import Project

RULES_FILE = Path("style") / "rules.toml"
SCOPES = ("asset", "category", "project")


@dataclass(frozen=True)
class Promoted:
    rule: str
    scope: str  # "project" | "category:<name>" | "asset:<rel>"
    reason: str

    def covers(self, asset: Asset) -> bool:
        if self.scope == "project":
            return True
        if self.scope == f"asset:{asset.rel}":
            return True
        return asset.category is not None and self.scope == f"category:{asset.category}"


def load_promoted(project: Project) -> list[Promoted]:
    path = project.root / RULES_FILE
    if not path.is_file():
        return []
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return [Promoted(p["rule"], p["scope"], p.get("reason", "")) for p in data.get("promoted", [])]


def scope_key(asset: Asset, scope: str) -> str:
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {', '.join(SCOPES)}: {scope!r}")
    if scope == "project":
        return "project"
    if scope == "category":
        if asset.category is None:
            raise ValueError(f"{asset.rel} has no category")
        return f"category:{asset.category}"
    return f"asset:{asset.rel}"


def promote(asset: Asset, rule: str, reason: str, scope: str = "asset") -> Promoted:
    """Record a style rule; idempotent for the same rule and scope."""
    entry = Promoted(rule, scope_key(asset, scope), reason)
    existing = load_promoted(asset.project)
    if any(p.rule == rule and p.scope == entry.scope for p in existing):
        return entry
    path = asset.project.root / RULES_FILE
    data: dict[str, Any] = {}
    if path.is_file():
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    data.setdefault("promoted", []).append(
        {"rule": entry.rule, "scope": entry.scope, "reason": entry.reason}
    )
    write_toml(path, data)
    return entry


def suppressed(asset: Asset, rule: str) -> bool:
    """True when the rule is off for this asset or was promoted away in its scope."""
    if asset.settings().checks.get(rule) == "off":
        return True
    return any(p.rule == rule and p.covers(asset) for p in load_promoted(asset.project))


def raise_check_issues(log: IssueLog, version: str, results: list[CheckResult]) -> list[Issue]:
    """Turn flagged check results into `script` issues, skipping suppressed rules and
    rules that already have an open issue on this version."""
    open_rules = {
        i.rule for i in log.state().issues.values() if i.state == "open" and i.version == version
    }
    raised = []
    for r in results:
        if not r.flagged or r.rule in open_rules or suppressed(log.asset, r.rule):
            continue
        raised.append(
            log.raise_issue(
                f"{r.check}: {r.status} ({r.value:g})",
                author="script",
                kind="rule",
                version=version,
                rule=r.rule,
                areas=[{"box": list(b)} for b in r.regions],
            )
        )
        open_rules.add(r.rule)
    return raised
