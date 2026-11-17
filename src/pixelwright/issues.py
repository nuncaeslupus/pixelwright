"""Issues and fixes of one asset, kept in an append-only `issues.jsonl`.

An issue says what is wrong and where; a fix is a candidate image that solves it.
Accepting fixes writes the next version. Every change is a new line, so the log is
the whole history; the current state is a fold over it.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from PIL import Image, ImageChops

from pixelwright.asset import Asset, AssetError
from pixelwright.workspace.files import append_jsonl

ISSUES_FILE = "issues.jsonl"
FIXES_DIR = "fixes"
AUTHORS = ("script", "ai", "person")
KINDS = ("rule", "critique", "note", "request")


class IssueError(ValueError):
    """An issue or fix operation is not valid in the current state."""


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@dataclass
class Fix:
    id: str
    issue: str
    by: str
    image: str
    base: str
    op: dict[str, Any] | None = None
    state: str = "proposed"  # proposed | accepted | rejected
    result_version: str | None = None
    reason: str | None = None


@dataclass
class Issue:
    id: str
    version: str
    author: str
    kind: str
    message: str
    areas: list[dict[str, Any]] = field(default_factory=list)
    target: str | None = None
    rule: str | None = None
    state: str = "open"  # open | fixed | rejected
    reason: str | None = None
    promote: bool = False
    replies: list[dict[str, str]] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)


@dataclass
class LogState:
    issues: dict[str, Issue] = field(default_factory=dict)
    fixes: dict[str, Fix] = field(default_factory=dict)
    # accept groups in order: (version written, fix ids, undone?, version before)
    groups: list[dict[str, Any]] = field(default_factory=list)


def _check(value: str, allowed: tuple[str, ...], what: str) -> str:
    if value not in allowed:
        raise IssueError(f"{what} must be one of {', '.join(allowed)}: {value!r}")
    return value


class IssueLog:
    def __init__(self, asset: Asset) -> None:
        self.asset = asset
        self.file = asset.path / ISSUES_FILE

    # --- reading ---------------------------------------------------------------

    def records(self) -> list[dict[str, Any]]:
        if not self.file.is_file():
            return []
        with self.file.open(encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def state(self) -> LogState:
        st = LogState()
        for r in self.records():
            event = r.get("event")
            if event is None:
                st.issues[r["id"]] = Issue(
                    id=r["id"],
                    version=r["version"],
                    author=r["author"],
                    kind=r["kind"],
                    message=r["message"],
                    areas=list(r.get("areas", [])),
                    target=r.get("target"),
                    rule=r.get("rule"),
                )
            elif event == "fix":
                st.fixes[r["id"]] = Fix(
                    id=r["id"],
                    issue=r["issue"],
                    by=r["by"],
                    image=r["image"],
                    base=r["base"],
                    op=r.get("op"),
                )
                st.issues[r["issue"]].fixes.append(r["id"])
            elif event == "reply":
                st.issues[r["id"]].replies.append(
                    {"by": r["by"], "message": r["message"], "at": r["at"]}
                )
            elif event == "fixed":
                st.issues[r["id"]].state = "fixed"
            elif event == "rejected" and r["id"] in st.issues:
                issue = st.issues[r["id"]]
                issue.state, issue.reason = "rejected", r.get("reason")
                issue.promote = bool(r.get("promote"))
            elif event == "rejected":
                fix = st.fixes[r["id"]]
                fix.state, fix.reason = "rejected", r.get("reason")
            elif event == "accepted":
                st.groups.append(
                    {
                        "version": r["result_version"],
                        "fixes": list(r["fixes"]),
                        "before": r["before"],
                        "undone": False,
                    }
                )
                self._apply(st, r["fixes"], r["result_version"])
            elif event == "undone":
                group = next(g for g in st.groups if g["version"] == r["id"])
                group["undone"] = True
                for fid in group["fixes"]:
                    fix = st.fixes[fid]
                    fix.state, fix.result_version = "proposed", None
                    st.issues[fix.issue].state = "open"
            elif event == "redone":
                group = next(g for g in st.groups if g["version"] == r["id"])
                group["undone"] = False
                self._apply(st, group["fixes"], r["result_version"])
        return st

    @staticmethod
    def _apply(st: LogState, fix_ids: list[str], version: str) -> None:
        for fid in fix_ids:
            fix = st.fixes[fid]
            fix.state, fix.result_version = "accepted", version
            st.issues[fix.issue].state = "fixed"

    def issue(self, issue_id: str) -> Issue:
        st = self.state()
        if issue_id not in st.issues:
            raise IssueError(f"{self.asset.rel}: no issue {issue_id}")
        return st.issues[issue_id]

    def open_issues(self) -> list[Issue]:
        return [i for i in self.state().issues.values() if i.state == "open"]

    def pending_for_ai(self) -> list[Issue]:
        """Open issues waiting on the AI: a request with no fix yet, or a person's reply
        that came after the last fix."""
        st = self.state()
        pending = []
        for issue in st.issues.values():
            if issue.state != "open":
                continue
            last_reply = issue.replies[-1] if issue.replies else None
            asked = issue.target == "ai" and not issue.fixes
            replied = bool(last_reply and last_reply["by"] == "person" and issue.fixes)
            if asked or replied:
                pending.append(issue)
        return pending

    # --- writing ---------------------------------------------------------------

    def _append(self, record: dict[str, Any]) -> dict[str, Any]:
        record = {"id": record.pop("id"), "at": _now(), **record}
        append_jsonl(self.file, record)
        return record

    def raise_issue(
        self,
        message: str,
        *,
        author: str,
        kind: str = "note",
        version: str | None = None,
        areas: list[dict[str, Any]] | None = None,
        target: str | None = None,
        rule: str | None = None,
    ) -> Issue:
        _check(author, AUTHORS, "author")
        _check(kind, KINDS, "kind")
        if target not in (None, "ai"):
            raise IssueError(f"target must be 'ai' or empty: {target!r}")
        version = version or self.asset.latest()
        if version is None:
            raise IssueError(f"{self.asset.rel}: no version to raise an issue on")
        self.asset.version_path(version)
        issue_id = _new_id("i")
        self._append(
            {
                "id": issue_id,
                "version": version,
                "author": author,
                "target": target,
                "kind": kind,
                "rule": rule,
                "areas": areas or [],
                "message": message,
                "state": "open",
            }
        )
        return self.issue(issue_id)

    def propose_fix(
        self,
        issue_id: str,
        image: Image.Image,
        *,
        by: str,
        base: str | None = None,
        op: dict[str, Any] | None = None,
    ) -> Fix:
        """Store a candidate image for an issue. `base` is the version it was computed on."""
        _check(by, AUTHORS, "by")
        issue = self.issue(issue_id)
        if issue.state != "open":
            raise IssueError(f"issue {issue_id} is {issue.state}")
        base = base or self.asset.latest() or issue.version
        with Image.open(self.asset.version_path(base)) as base_img:
            if base_img.size != image.size:
                raise IssueError(f"fix size {image.size} differs from {base} {base_img.size}")
        fix_id = _new_id("f")
        rel = f"{FIXES_DIR}/{fix_id}.png"
        (self.asset.path / FIXES_DIR).mkdir(exist_ok=True)
        image.save(self.asset.path / rel, format="PNG")
        self._append(
            {"id": fix_id, "event": "fix", "issue": issue_id, "by": by, "image": rel,
             "base": base, "op": op}
        )  # fmt: skip
        return self.state().fixes[fix_id]

    def reply(self, issue_id: str, message: str, *, by: str) -> None:
        _check(by, AUTHORS, "by")
        self.issue(issue_id)
        self._append({"id": issue_id, "event": "reply", "by": by, "message": message})

    def reject_issue(
        self,
        issue_id: str,
        reason: str,
        *,
        by: str = "person",
        promote: bool = False,
        scope: str = "asset",
    ) -> None:
        """Reject an issue. With `promote`, its rule is written to `style/rules.toml` for
        `scope` (asset, category or project) and checks stop raising it there."""
        if not reason.strip():
            raise IssueError("a rejection needs a reason")
        issue = self.issue(issue_id)
        if issue.state != "open":
            raise IssueError(f"issue {issue_id} is not open")
        if promote:
            if not issue.rule:
                raise IssueError("only an issue raised by a rule can be promoted")
            from pixelwright.rules import promote as promote_rule

            try:
                promote_rule(self.asset, issue.rule, reason, scope)
            except ValueError as exc:
                raise IssueError(str(exc)) from exc
        self._append(
            {"id": issue_id, "event": "rejected", "by": by, "reason": reason, "promote": promote}
        )

    def reject_fix(self, fix_id: str, reason: str, *, by: str = "person") -> None:
        if not reason.strip():
            raise IssueError("a rejection needs a reason")
        fix = self._fix(fix_id)
        if fix.state != "proposed":
            raise IssueError(f"fix {fix_id} is {fix.state}")
        self._append({"id": fix_id, "event": "rejected", "by": by, "reason": reason})

    def mark_fixed(self, issue_id: str, *, by: str = "person") -> None:
        """For a fix made outside the app (e.g. in Aseprite, saved as a new version)."""
        if self.issue(issue_id).state != "open":
            raise IssueError(f"issue {issue_id} is not open")
        self._append({"id": issue_id, "event": "fixed", "by": by})

    def _fix(self, fix_id: str) -> Fix:
        fixes = self.state().fixes
        if fix_id not in fixes:
            raise IssueError(f"{self.asset.rel}: no fix {fix_id}")
        return fixes[fix_id]

    def accept(self, fix_ids: list[str], *, by: str = "person") -> str:
        """Accept one or several fixes together; writes exactly one new version.

        Each fix contributes the pixels where its candidate differs from its base,
        laid over the current version in the order given.
        """
        if not fix_ids or len(set(fix_ids)) != len(fix_ids):
            raise IssueError("accept takes one or more distinct fix ids")
        st = self.state()
        fixes = []
        for fid in fix_ids:
            if fid not in st.fixes:
                raise IssueError(f"{self.asset.rel}: no fix {fid}")
            if st.fixes[fid].state != "proposed":
                raise IssueError(f"fix {fid} is {st.fixes[fid].state}")
            fixes.append(st.fixes[fid])
        before = self.asset.latest()
        if before is None:
            raise AssetError(f"{self.asset.rel}: no version")
        with Image.open(self.asset.version_path(before)) as cur:
            result = cur.convert("RGBA")
        for fix in fixes:
            with (
                Image.open(self.asset.path / fix.image) as cand_raw,
                Image.open(self.asset.version_path(fix.base)) as base_raw,
            ):
                cand, base = cand_raw.convert("RGBA"), base_raw.convert("RGBA")
                if len(fixes) == 1 and fix.base == before:
                    result = cand
                    break
                diff = ImageChops.difference(cand, base).convert("L").point(lambda v: 255 * (v > 0))
                result.paste(cand, (0, 0), diff)
        version = self.asset.add_version(result)
        self._append(
            {"id": version, "event": "accepted", "by": by, "fixes": fix_ids,
             "result_version": version, "before": before}
        )  # fmt: skip
        return version

    def _write_copy(self, name: str) -> str:
        with Image.open(self.asset.version_path(name)) as img:
            img.load()
            return self.asset.add_version(img)

    def undo(self, *, by: str = "person") -> str:
        """Undo the last accept: its fixes and issues reopen, and the version before it
        is current again (written as a new version, so nothing is overwritten)."""
        live = [g for g in self.state().groups if not g["undone"]]
        if not live:
            raise IssueError("nothing to undo")
        group = live[-1]
        version = self._write_copy(group["before"])
        self._append(
            {"id": group["version"], "event": "undone", "by": by, "result_version": version}
        )
        return version

    def redo(self, *, by: str = "person") -> str:
        groups = self.state().groups
        if not groups or not groups[-1]["undone"]:
            raise IssueError("nothing to redo")
        trailing = len(groups)
        while trailing > 0 and groups[trailing - 1]["undone"]:
            trailing -= 1
        group = groups[trailing]  # the most recently undone group comes back first
        version = self._write_copy(group["version"])
        self._append(
            {"id": group["version"], "event": "redone", "by": by, "result_version": version}
        )
        return version
