"""Minimal MCP server (JSON-RPC 2.0, newline-delimited over stdio) built from the registry."""

from __future__ import annotations

import base64
import json
import sys
import time
from importlib.metadata import version as package_version
from pathlib import Path
from typing import IO, Any

from pixelwright.cli import as_error, envelope, find_workspace, run
from pixelwright.cli.registry import EXIT_USAGE, REGISTRY, Command, Param, PwError
from pixelwright.core.image import RGBImage
from pixelwright.core.render import upscale
from pixelwright.io.png import encode_png, read_png

PROTOCOL = "2025-06-18"
MAX_IMAGE = 1024
_JSON_TYPES = {"str": "string", "int": "integer", "float": "number", "bool": "boolean"}
_PY_TYPES: dict[str, tuple[type, ...]] = {
    "str": (str,),
    "int": (int,),
    "float": (int, float),
    "bool": (bool,),
}
WORKSPACE = Param("workspace", help="workspace folder (default: the server's)")


def _property(p: Param) -> dict[str, Any]:
    item: dict[str, Any] = {"type": "string"} if p.kind == "list" else {"type": _JSON_TYPES[p.kind]}
    if p.choices:
        item["enum"] = list(p.choices)
    prop = {"type": "array", "items": item} if p.kind == "list" else item
    if p.help:
        prop["description"] = p.help
    if p.default is not None:
        prop["default"] = p.default
    return prop


def tool_schema(cmd: Command) -> dict[str, Any]:
    params = (*cmd.params, WORKSPACE)
    return {
        "name": cmd.name,
        "description": cmd.help,
        "inputSchema": {
            "type": "object",
            "properties": {p.name: _property(p) for p in params},
            "required": [p.name for p in params if p.required],
            "additionalProperties": False,
        },
    }


def tools() -> list[dict[str, Any]]:
    return [tool_schema(cmd) for cmd in REGISTRY.values()]


def _arguments(cmd: Command, raw: object) -> dict[str, Any]:
    args = dict(raw) if isinstance(raw, dict) else {}
    known = {p.name: p for p in (*cmd.params, WORKSPACE)}
    unknown = set(args) - set(known)
    if unknown:
        raise PwError("usage", f"unknown arguments: {sorted(unknown)}", exit_code=EXIT_USAGE)
    for name, p in known.items():
        if p.required and args.get(name) is None:
            raise PwError("usage", f"missing argument: {name}", exit_code=EXIT_USAGE)
        value = args.get(name)
        if value is None:
            continue
        values = value if p.kind == "list" else [value]
        ok = isinstance(values, list) and all(
            isinstance(v, _PY_TYPES.get(p.kind, (str,)))
            and not (isinstance(v, bool) and p.kind in ("int", "float"))
            for v in values
        )
        if not ok or (p.choices and any(v not in p.choices for v in values)):
            raise PwError("usage", f"invalid value for {name}: {value!r}", exit_code=EXIT_USAGE)
    return args


def _image_content(path: Path, scale: int) -> dict[str, Any]:
    """The render at native size, integer-upscaled so its longest side stays <= 1024 px."""
    native = read_png(path).to_rgba()[::scale, ::scale]
    factor = max(1, MAX_IMAGE // max(native.shape[:2]))
    png = encode_png(RGBImage(upscale(native, factor)))
    return {"type": "image", "data": base64.b64encode(png).decode(), "mimeType": "image/png"}


def call_tool(name: str, raw: object, workspace: Path | None) -> dict[str, Any]:
    started = time.perf_counter()
    cmd = REGISTRY.get(name)
    try:
        if cmd is None:
            raise PwError("usage", f"unknown tool: {name}", exit_code=EXIT_USAGE)
        args = _arguments(cmd, raw)
        root = Path(args.pop("workspace")) if args.get("workspace") else workspace
        if name == "view":  # never block the MCP server; it keeps the viewer alive
            args["background"] = True
        outcome = run(cmd, args, root)
    except (PwError, OSError, ValueError) as exc:
        error = as_error(exc)
        env = envelope(name, started, error)
        text = json.dumps(env, default=str)
        return {
            "content": [{"type": "text", "text": text}],
            "structuredContent": env,
            "isError": True,
        }
    env = envelope(name, started, outcome)
    content: list[dict[str, Any]] = [{"type": "text", "text": json.dumps(env, default=str)}]
    if name == "render" and outcome.outputs:
        base = find_workspace((root or Path.cwd()).resolve())
        default = next(p.default for p in REGISTRY["render"].params if p.name == "scale")
        scale = int(args.get("scale") or default)
        content.append(_image_content(base / outcome.outputs[0], scale))
    return {"content": content, "structuredContent": env, "isError": False}


def handle(message: dict[str, Any], workspace: Path | None = None) -> dict[str, Any] | None:
    """Answer one JSON-RPC message; notifications (no id) get no answer."""
    if "id" not in message:
        return None
    method, params = message.get("method"), message.get("params") or {}
    reply: dict[str, Any] = {"jsonrpc": "2.0", "id": message["id"]}
    if method == "initialize":
        reply["result"] = {
            "protocolVersion": params.get("protocolVersion", PROTOCOL),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "pixelwright", "version": package_version("pixelwright")},
        }
    elif method == "ping":
        reply["result"] = {}
    elif method == "tools/list":
        reply["result"] = {"tools": tools()}
    elif method == "tools/call":
        reply["result"] = call_tool(str(params.get("name")), params.get("arguments"), workspace)
    else:
        reply["error"] = {"code": -32601, "message": f"method not found: {method}"}
    return reply


def serve(
    stdin: IO[str] | None = None, stdout: IO[str] | None = None, workspace: Path | None = None
) -> int:
    src, out = stdin or sys.stdin, stdout or sys.stdout
    for line in src:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            reply: dict[str, Any] | None = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "parse error"},
            }
        else:
            reply = handle(message, workspace) if isinstance(message, dict) else None
        if reply is not None:
            out.write(json.dumps(reply, default=str) + "\n")
            out.flush()
    return 0
