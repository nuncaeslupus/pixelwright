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

    def stage(self, version: str) -> str:
        """Current stage of a version: its meta stage, overridden by the last decision."""
        stage = str(self.meta(version)["stage"])
        for rec in self.history():
            if rec["event"] == "decision" and rec.get("version") == version:
                stage = "approved" if rec["decision"] == "approve" else "draft"
        return stage

    # -- masks --------------------------------------------------------------
    @property
    def masks_index(self) -> Path:
        return self.path / "masks" / "masks.yaml"

    def masks(self) -> list[dict[str, Any]]:
        if not self.masks_index.exists():
            return []
        entries = schema.validate("masks", read_yaml(self.masks_index))["masks"]
        return list(entries)

    def add_mask(
        self, mask_id: str, png: bytes, *, rule: str = "", note: str = "", author: str = "human"
    ) -> Path:
        check_asset_id(mask_id)
        entries = self.masks()
        if any(m["id"] == mask_id for m in entries):
            raise FileExistsError(f"mask already exists: {mask_id}")
        file = self.path / "masks" / f"{mask_id}.png"
        write_bytes_atomic(file, png)
        entries.append(
            {
                "id": mask_id,
                "file": f"masks/{mask_id}.png",
                "rule": rule,
                "note": note,
                "author": _check_author(author),
                "created": utc_now(),
            }
        )
        write_yaml(self.masks_index, schema.stamp("masks", {"masks": entries}))
        return file


def _check_author(author: str) -> str:
    if author not in AUTHORS:
        raise ValueError(f"author must be one of {AUTHORS}")
    return author
