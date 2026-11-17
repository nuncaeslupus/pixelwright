"""`pw`: the pixelwright command line. Every command prints a JSON envelope with `--json`."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NoReturn

from pixelwright.bench import commands as _bench  # noqa: F401  (registers `bench`)
from pixelwright.cli import bridge_commands as _bridge  # noqa: F401  (wait, requests)
from pixelwright.cli import commands as _commands  # noqa: F401  (registers the commands)
from pixelwright.cli import gen_commands as _gen_commands  # noqa: F401  (generation commands)
from pixelwright.cli import tour as _tour  # noqa: F401  (registers `tour`)
from pixelwright.cli.registry import (
    EXIT_USAGE,
    EXIT_VALIDATION,
    REGISTRY,
    Command,
    Outcome,
    Param,
    PwError,
)
from pixelwright.core.providers.base import ProviderError
from pixelwright.viewer import command as _view  # noqa: F401  (registers `view`)
from pixelwright.workspace.config import CONFIG_NAME
from pixelwright.workspace.schema import SchemaError

__all__ = ["REGISTRY", "build_parser", "main", "run"]

_TYPES: dict[str, type] = {"str": str, "int": int, "float": float, "list": str}


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise PwError("usage", message, exit_code=EXIT_USAGE)


def _add(parser: argparse.ArgumentParser, p: Param) -> None:
    kw: dict[str, Any] = {"help": p.help}
    if p.kind == "bool":
        parser.add_argument(p.flag, dest=p.name, action="store_true", **kw)
        return
    kw["type"] = _TYPES[p.kind]
    if p.choices:
        kw["choices"] = p.choices
    if p.kind == "list":
        kw.update(action="extend", nargs="+", default=[])
    else:
        kw["default"] = p.default
    if p.positional:
        if not p.required and p.kind != "list":
            kw["nargs"] = "?"
        parser.add_argument(p.name, **kw)
    else:
        parser.add_argument(p.flag, dest=p.name, required=p.required, **kw)


def build_parser() -> argparse.ArgumentParser:
    common = _Parser(add_help=False)
    common.add_argument("--workspace", type=Path, help="workspace folder (default: nearest)")
    common.add_argument("--json", action="store_true", help="print the JSON envelope")
    parser = _Parser(
        prog="pw",
        description=__doc__,
        epilog="New here? Run `pw tour`. Guide: docs/guide/how-it-works.md",
    )
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    for cmd in REGISTRY.values():
        child = sub.add_parser(cmd.name, help=cmd.help, description=cmd.help, parents=[common])
        for p in cmd.params:
            _add(child, p)
    return parser


def find_workspace(start: Path) -> Path:
    for folder in (start, *start.parents):
        if (folder / CONFIG_NAME).is_file():
            return folder
    raise PwError("no_workspace", f"no {CONFIG_NAME} in {start} or its parents; run `pw init`")


def run(cmd: Command, args: dict[str, Any], workspace: Path | None = None) -> Outcome:
    """Run one command with already-parsed arguments (also used by the MCP server)."""
    full = {p.name: args.get(p.name, [] if p.kind == "list" else p.default) for p in cmd.params}
    if cmd.needs_workspace:
        root = find_workspace((workspace or Path.cwd()).resolve())
    else:
        root = (workspace or Path.cwd()).resolve()
    return cmd.run(root, full)


def envelope(name: str | None, started: float, outcome: Outcome | PwError) -> dict[str, Any]:
    ms = round((time.perf_counter() - started) * 1000)
    if isinstance(outcome, PwError):
        error = {"code": outcome.code, "message": outcome.message, "details": outcome.details}
        return {"ok": False, "command": name, "error": error, "duration_ms": ms}
    return {
        "ok": True,
        "command": name,
        "asset": outcome.asset,
        "version": outcome.version,
        "stage": outcome.stage,
        "outputs": outcome.outputs,
        "data": outcome.data,
        "warnings": outcome.warnings,
        "duration_ms": ms,
    }


def as_error(exc: Exception) -> PwError:
    if isinstance(exc, PwError):
        return exc
    if isinstance(exc, ProviderError):
        return PwError(exc.code, exc.message, exit_code=exc.exit_code, details=exc.details)
    for kind, code in (
        (SchemaError, "schema_error"),
        (FileNotFoundError, "not_found"),
        (FileExistsError, "exists"),
        (ValueError, "invalid"),
    ):
        if isinstance(exc, kind):
            return PwError(code, str(exc), exit_code=EXIT_VALIDATION)
    raise exc


def _jsonable(value: object) -> object:
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    if isinstance(value, (tuple, set)):
        return list(value)
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")


def _mcp(argv: list[str]) -> int:
    from pixelwright.mcp import serve

    parser = argparse.ArgumentParser(prog="pw mcp", description="MCP server over stdio")
    parser.add_argument("--workspace", type=Path, help="default workspace folder")
    return serve(workspace=parser.parse_args(argv).workspace)


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["mcp"]:
        return _mcp(argv[1:])
    started = time.perf_counter()
    as_json = "--json" in argv
    name = next((a for a in argv if a in REGISTRY), None)
    try:
        ns = vars(build_parser().parse_args(argv))
        name = ns.pop("command")
        ns.pop("json")
        outcome: Outcome | PwError = run(REGISTRY[name], ns, ns.pop("workspace"))
    except (PwError, SchemaError, OSError, ValueError) as exc:
        outcome = as_error(exc)
    env = envelope(name, started, outcome)
    if as_json:
        print(json.dumps(env, default=_jsonable))
    elif isinstance(outcome, PwError):
        print(f"pw {name or ''}: {outcome.code}: {outcome.message}", file=sys.stderr)
    elif outcome.text:
        print(outcome.text)
    else:
        print(
            json.dumps(
                {k: env[k] for k in ("asset", "version", "outputs", "data") if env[k]},
                default=_jsonable,
                indent=1,
            )
        )
        for warning in outcome.warnings:
            print(f"warning: {warning}", file=sys.stderr)
    return outcome.exit_code if isinstance(outcome, PwError) else 0
