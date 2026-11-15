"""File-format schema tags (`schema: pixelwright/<name>@<major>`) and light validation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PREFIX = "pixelwright/"

# Current major of every file format.
CURRENT: dict[str, int] = {
    "workspace": 1,
    "asset": 1,
    "meta": 1,
    "history": 1,
    "masks": 1,
}

# Required top-level keys and their types, per format.
_REQUIRED: dict[str, dict[str, type | tuple[type, ...]]] = {
    "workspace": {"roles": dict, "canvas": dict, "commit": list},
    "asset": {"id": str, "kind": str, "canvas": dict, "stage": str},
    "meta": {
        "version": str,
        "parent": (str, type(None)),
        "step": str,
        "params": dict,
        "stage": str,
        "created": str,
        "inputs": dict,
        "outputs": dict,
    },
    "history": {"event": str, "time": str},
    "masks": {"masks": list},
}


class SchemaError(ValueError):
    """A file does not carry a schema this version of pixelwright can read."""


def tag(name: str) -> str:
    return f"{PREFIX}{name}@{CURRENT[name]}"


def stamp(name: str, data: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of `data` with the schema tag as its first key."""
    return {"schema": tag(name), **{k: v for k, v in data.items() if k != "schema"}}


def parse_tag(value: object) -> tuple[str, int]:
    if not isinstance(value, str) or not value.startswith(PREFIX) or "@" not in value:
        raise SchemaError(f"missing or malformed schema tag: {value!r}")
    name, _, major = value[len(PREFIX) :].partition("@")
    if not major.isdigit():
        raise SchemaError(f"malformed schema major in {value!r}")
    return name, int(major)


def validate(name: str, data: object) -> dict[str, Any]:
    """Check tag, major and required keys; return the data as a dict."""
    if not isinstance(data, dict):
        raise SchemaError(f"{name}: expected a mapping, got {type(data).__name__}")
    found, major = parse_tag(data.get("schema"))
    if found != name:
        raise SchemaError(f"expected schema {name!r}, found {found!r}")
    if major > CURRENT[name]:
        raise SchemaError(
            f"{name}@{major} is newer than this pixelwright reads (@{CURRENT[name]}); upgrade"
        )
    if major < CURRENT[name]:
        raise SchemaError(f"{name}@{major} is older than @{CURRENT[name]}; run `pw migrate`")
    for key, typ in _REQUIRED[name].items():
        if key not in data:
            raise SchemaError(f"{name}: missing key {key!r}")
        if not isinstance(data[key], typ):
            raise SchemaError(f"{name}: key {key!r} has type {type(data[key]).__name__}")
    return data
