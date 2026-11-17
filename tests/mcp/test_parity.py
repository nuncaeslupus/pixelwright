import io
import json
from pathlib import Path
from typing import Any

import numpy as np

from pixelwright.cli import REGISTRY, build_parser
from pixelwright.core.image import RGBImage
from pixelwright.io.png import write_png
from pixelwright.mcp import handle, serve, tools


def _cli_params(name: str) -> set[str]:
    sub = next(a for a in build_parser()._actions if a.dest == "command")
    parser = sub.choices[name]  # type: ignore[index]
    return {a.dest for a in parser._actions if a.dest not in ("help", "json")}


def test_every_cli_command_has_matching_mcp_tool() -> None:
    listed = {t["name"]: t for t in tools()}
    assert set(listed) == set(REGISTRY)
    for name, cmd in REGISTRY.items():
        schema = listed[name]["inputSchema"]
        assert set(schema["properties"]) == _cli_params(name)
        assert set(schema["required"]) == {p.name for p in cmd.params if p.required}
        for p in cmd.params:
            prop = schema["properties"][p.name]
            enum = prop.get("items", prop).get("enum")
            assert enum == (list(p.choices) if p.choices else None)


def call(ws: Path, name: str, **arguments: Any) -> dict[str, Any]:
    msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    reply = handle(msg, ws)
    assert reply is not None
    result: dict[str, Any] = reply["result"]
    return result


def test_tools_call_returns_envelope(tmp_path: Path) -> None:
    ws = tmp_path / "art"
    assert call(ws, "init")["structuredContent"]["ok"]
    rgba = np.zeros((12, 16, 4), np.uint8)
    rgba[..., 3] = 255
    write_png(tmp_path / "src.png", RGBImage(rgba))
    added = call(ws, "add", asset="sprites/hero", **{"from": str(tmp_path / "src.png")})
    assert not added["isError"] and added["structuredContent"]["command"] == "add"
    assert added["content"][0]["type"] == "text"
    bad = call(ws, "palette", action="sepia")
    assert bad["isError"] and bad["structuredContent"]["error"]["code"] == "usage"
    missing = call(ws, "check", asset="sprites/ghost")
    assert missing["isError"] and missing["structuredContent"]["error"]["code"] == "no_asset"


def test_stdio_protocol() -> None:
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "x"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "nope"},
    ]
    out = io.StringIO()
    serve(io.StringIO("\n".join(json.dumps(m) for m in lines) + "\nnot json\n"), out)
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [r["id"] for r in replies] == [1, 2, 3, None]
    assert replies[0]["result"]["protocolVersion"] == "x"
    assert len(replies[1]["result"]["tools"]) == len(REGISTRY)
    assert replies[2]["error"]["code"] == -32601 and replies[3]["error"]["code"] == -32700
