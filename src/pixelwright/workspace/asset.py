"""One asset folder: spec, immutable versions, append-only history, masks."""

from __future__ import annotations

import errno
import json
import os
import re
import shutil
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pixelwright.workspace import schema
from pixelwright.workspace.files import (
    append_jsonl,
    read_yaml,
    sha256_bytes,
    write_bytes_atomic,
    write_yaml,
)

KINDS = ("background", "sprite", "prop", "animation", "effect", "tileset")
DECISIONS = ("approve", "reject")
AUTHORS = ("human", "claude", "check")
ISSUE_STATUS = ("open", "fixed")
REGIONS = ("mask", "box", "image")
ASSET_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
VERSION = re.compile(r"^v(\d{4,})$")
FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SUBDIRS = ("inputs", "drafts", "versions", "masks", "export")
_RESERVED_FILES = {"meta.yaml"}
_META_CORE = {
    "schema",
    "version",
    "parent",
    "step",
    "params",
    "stage",
    "created",
    "inputs",
    "outputs",
}


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def check_asset_id(asset_id: str) -> str:
    if not ASSET_ID.fullmatch(asset_id):
        raise ValueError(f"asset id must be lowercase kebab-case: {asset_id!r}")
    return asset_id


def _check_file_name(name: str) -> str:
    if not FILE_NAME.fullmatch(name) or name in _RESERVED_FILES:
        raise ValueError(f"invalid version file name: {name!r}")
    return name


class Asset:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.id = check_asset_id(path.name)

    # -- spec ---------------------------------------------------------------
    @property
    def spec_path(self) -> Path:
        return self.path / "asset.yaml"

    def spec(self) -> dict[str, Any]:
        return schema.validate("asset", read_yaml(self.spec_path))

    def update_spec(self, **fields: Any) -> None:
        """Change top-level fields of `asset.yaml` (e.g. the palette)."""
        write_yaml(self.spec_path, schema.stamp("asset", {**self.spec(), **fields}))

    @classmethod
    def create(cls, path: Path, kind: str, canvas: Mapping[str, int], **fields: Any) -> Asset:
        if kind not in KINDS:
            raise ValueError(f"unknown asset kind {kind!r}; one of {KINDS}")
        check_asset_id(path.name)
        if path.exists():
            raise FileExistsError(f"asset already exists: {path}")
        for sub in SUBDIRS:
            (path / sub).mkdir(parents=True)
        asset = cls(path)
        data = {"id": asset.id, "kind": kind, "canvas": dict(canvas), "stage": "draft", **fields}
        write_yaml(asset.spec_path, schema.stamp("asset", data))
        asset._log({"event": "created", "kind": kind})
        return asset

    # -- versions -----------------------------------------------------------
    @property
    def versions_dir(self) -> Path:
        return self.path / "versions"

    def versions(self) -> list[str]:
        names = [p.name for p in self.versions_dir.iterdir() if VERSION.fullmatch(p.name)]
        return sorted(names, key=lambda n: int(n[1:]))

    def latest(self) -> str | None:
        found = self.versions()
        return found[-1] if found else None

    def meta(self, version: str) -> dict[str, Any]:
        return schema.validate("meta", read_yaml(self.versions_dir / version / "meta.yaml"))

    def new_version(
        self,
        step: str,
        files: Mapping[str, bytes],
        *,
        params: Mapping[str, Any] | None = None,
        parent: str | None = None,
        inputs: Mapping[str, str] | None = None,
        **extra: Any,
    ) -> str:
        """Write a new immutable version folder and log it; return its name (`v0001`...).

        `files` maps file names (e.g. `image.png`) to their bytes; `inputs` maps input
        names to SHA-256 hashes. `extra` carries provider, request_hash, cost, seed...
        """
        if not files:
            raise ValueError("a version needs at least one file")
        clash = set(extra) & _META_CORE
        if clash:
            raise ValueError(f"reserved meta keys cannot be passed as extras: {sorted(clash)}")
        if parent is not None and not (self.versions_dir / parent / "meta.yaml").is_file():
            raise FileNotFoundError(f"parent version not found: {parent}")
        tmp = self.versions_dir / f".tmp-{uuid.uuid4().hex}"
        tmp.mkdir()
        try:
            outputs = {}
            for name, data in files.items():
                write_bytes_atomic(tmp / _check_file_name(name), data)
                outputs[name] = sha256_bytes(data)
            return self._publish(tmp, step, params, parent, inputs, outputs, extra)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise

    def _publish(
        self,
        tmp: Path,
        step: str,
        params: Mapping[str, Any] | None,
        parent: str | None,
        inputs: Mapping[str, str] | None,
        outputs: dict[str, str],
        extra: Mapping[str, Any],
    ) -> str:
        for _ in range(100):
            latest = self.latest()
            name = f"v{(int(latest[1:]) if latest else 0) + 1:04d}"
            meta = schema.stamp(
                "meta",
                {
                    "version": name,
                    "parent": parent,
                    "step": step,
                    "params": dict(params or {}),
                    "stage": "draft",
                    "created": utc_now(),
                    "inputs": dict(inputs or {}),
                    "outputs": outputs,
                    **extra,
                },
            )
            write_yaml(tmp / "meta.yaml", meta)
            try:
                os.mkdir(self.versions_dir / name)  # reserve the name; fails if taken
            except FileExistsError:
                continue
            os.rename(tmp, self.versions_dir / name)  # empty reserved dir -> replaced
            self._log({"event": "step", "version": name, "step": step, "parent": parent})
            return name
        raise OSError(errno.EEXIST, "could not allocate a version name")

    # -- history ------------------------------------------------------------
    @property
    def history_path(self) -> Path:
        return self.path / "history.jsonl"

    def _log(self, record: dict[str, Any]) -> None:
        append_jsonl(self.history_path, schema.stamp("history", {"time": utc_now(), **record}))

    def history(self) -> list[dict[str, Any]]:
        if not self.history_path.exists():
            return []
        lines = self.history_path.read_text(encoding="utf-8").splitlines()
        return [schema.validate("history", json.loads(line)) for line in lines if line.strip()]

    def decide(self, version: str, decision: str, *, author: str = "human", note: str = "") -> None:
        if decision not in DECISIONS:
            raise ValueError(f"decision must be one of {DECISIONS}")
        self.meta(version)  # must exist and validate
        record = {"event": "decision", "version": version, "decision": decision}
        self._log({**record, "author": _check_author(author), "note": note})

    def note(self, text: str, *, author: str = "human", version: str | None = None) -> None:
        record = {"event": "note", "version": version, "note": text}
        self._log({**record, "author": _check_author(author)})

    def exported(self, version: str, files: list[str]) -> None:
        self.meta(version)
        self._log({"event": "export", "version": version, "files": files})

    def decisions(self) -> list[dict[str, Any]]:
        """Decision records still in force: each `decision_revert` cancels the latest one."""
        live: list[dict[str, Any]] = []
        for rec in self.history():
            if rec["event"] == "decision":
                live.append(rec)
            elif rec["event"] == "decision_revert" and live:
                live.pop()
        return live

    def revert_decision(self, *, author: str = "human") -> dict[str, Any]:
        """Undo the latest decision still in force; return the record it cancels."""
        live = self.decisions()
        if not live:
            raise ValueError(f"{self.id} has no decision to revert")
        last = live[-1]
        record = {"event": "decision_revert", "version": last["version"]}
        self._log({**record, "decision": last["decision"], "author": _check_author(author)})
        return last

    def stage(self, version: str) -> str:
        """Current stage: meta stage, then the last decision in force; an export makes it
        final."""
        if any(r["event"] == "export" and r.get("version") == version for r in self.history()):
            return "final"
        stage = str(self.meta(version)["stage"])
        for rec in self.decisions():
            if rec["version"] == version:
                stage = "approved" if rec["decision"] == "approve" else "draft"
        return stage

    def clear_masks(self) -> int:
        entries = self.masks()
        for entry in entries:
            if entry.get("file"):
                (self.path / entry["file"]).unlink(missing_ok=True)
        self.masks_index.unlink(missing_ok=True)
        return len(entries)

    # -- masks --------------------------------------------------------------
    @property
    def masks_index(self) -> Path:
        return self.path / "masks" / "masks.yaml"

    def masks(self) -> list[dict[str, Any]]:
        """Issue entries (`masks@2`); a `masks@1` file reads as open mask issues."""
        if not self.masks_index.exists():
            return []
        raw = read_yaml(self.masks_index)
        if isinstance(raw, dict) and raw.get("schema") == f"{schema.PREFIX}masks@1":
            raw = {**raw, "schema": schema.tag("masks")}
            raw["masks"] = [_upgrade_v1(e) for e in raw.get("masks") or []]
        entries = schema.validate("masks", raw)["masks"]
        return list(entries)

    issues = masks

    def issue(self, issue_id: str) -> dict[str, Any]:
        found = next((m for m in self.masks() if m["id"] == issue_id), None)
        if found is None:
            raise KeyError(f"{self.id} has no issue {issue_id}")
        return found

    def add_mask(
        self, mask_id: str, png: bytes, *, rule: str = "", note: str = "", author: str = "human"
    ) -> Path:
        self.add_issue(mask_id, png=png, rule=rule, note=note, author=author)
        return self.path / "masks" / f"{mask_id}.png"

    def add_issue(
        self,
        issue_id: str,
        *,
        png: bytes | None = None,
        box: tuple[int, int, int, int] | None = None,
        version: str | None = None,
        rule: str = "",
        note: str = "",
        author: str = "human",
    ) -> dict[str, Any]:
        """Record an issue on a region: a mask PNG, a box (x, y, w, h), or the whole image."""
        check_asset_id(issue_id)
        if png is not None and box is not None:
            raise ValueError("an issue has a mask or a box, not both")
        if version is not None:
            self.meta(version)
        entries = self.masks()
        if any(m["id"] == issue_id for m in entries):
            raise FileExistsError(f"issue already exists: {issue_id}")
        entry: dict[str, Any] = {"id": issue_id, "region": "image"}
        if png is not None:
            write_bytes_atomic(self.path / "masks" / f"{issue_id}.png", png)
            entry = {"id": issue_id, "region": "mask", "file": f"masks/{issue_id}.png"}
        elif box is not None:
            x, y, w, h = (int(v) for v in box)
            if w < 1 or h < 1 or x < 0 or y < 0:
                raise ValueError(f"box must be x,y,w,h with w,h >= 1: {box}")
            entry = {"id": issue_id, "region": "box", "box": [x, y, w, h]}
        entry.update(
            {
                "rule": rule,
                "note": note,
                "author": _check_author(author),
                "version": version,
                "status": "open",
                "fixed_in": None,
                "created": utc_now(),
            }
        )
        entries.append(entry)
        write_yaml(self.masks_index, schema.stamp("masks", {"masks": entries}))
        self._log({"event": "issue_add", "issue": issue_id, "version": version, "author": author})
        return entry

    def resolve_issue(
        self, issue_id: str, version: str, *, author: str = "human"
    ) -> dict[str, Any]:
        """Mark an issue fixed by `version`."""
        self.meta(version)
        entries = self.masks()
        entry = next((m for m in entries if m["id"] == issue_id), None)
        if entry is None:
            raise KeyError(f"{self.id} has no issue {issue_id}")
        entry.update({"status": "fixed", "fixed_in": version})
        write_yaml(self.masks_index, schema.stamp("masks", {"masks": entries}))
        record = {"event": "issue_resolve", "issue": issue_id, "version": version}
        self._log({**record, "author": _check_author(author)})
        return entry


def _upgrade_v1(entry: dict[str, Any]) -> dict[str, Any]:
    """A `masks@1` entry: always a mask region, version unknown, still open."""
    return {"region": "mask", "version": None, "status": "open", "fixed_in": None, **entry}


def _check_author(author: str) -> str:
    if author not in AUTHORS:
        raise ValueError(f"author must be one of {AUTHORS}")
    return author
