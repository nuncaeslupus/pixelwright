"""Atomic file helpers: write to a temp path, then rename into place."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import tomli_w
import yaml


def write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    write_bytes_atomic(path, text.encode("utf-8"))


def read_yaml(path: Path) -> object:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def write_toml(path: Path, data: dict[str, Any]) -> None:
    write_bytes_atomic(path, tomli_w.dumps(data).encode("utf-8"))


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Append one JSON line; a single write so concurrent appenders do not interleave."""
    line = json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())
