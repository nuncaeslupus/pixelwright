"""Command registry shared by the CLI and the MCP server: one declaration per command."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PARAM_KINDS = ("str", "int", "float", "bool", "list")

# Exit codes (spec §5, CLI result envelope).
EXIT_USAGE = 2
EXIT_VALIDATION = 3
EXIT_CHECK = 4


class PwError(Exception):
    """An error reported in the envelope: `code` is stable, `message` is for humans."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        exit_code: int = EXIT_VALIDATION,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.details = details or {}


@dataclass(frozen=True)
class Param:
    name: str  # snake_case; the CLI flag is --name-with-dashes
    kind: str = "str"
    help: str = ""
    required: bool = False
    default: Any = None
    choices: tuple[str, ...] = ()
    positional: bool = False

    def __post_init__(self) -> None:
        if self.kind not in PARAM_KINDS:
            raise ValueError(f"param kind must be one of {PARAM_KINDS}")

    @property
    def flag(self) -> str:
        return "--" + self.name.replace("_", "-")


@dataclass
class Outcome:
    """What a command returns; the envelope adds ok, command and duration."""

    asset: str | None = None
    version: str | None = None
    stage: str | None = None
    outputs: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


Handler = Callable[[Path, dict[str, Any]], Outcome]


@dataclass(frozen=True)
class Command:
    name: str
    help: str
    params: tuple[Param, ...]
    run: Handler
    needs_workspace: bool = True


REGISTRY: dict[str, Command] = {}


def command(
    name: str, help: str, *params: Param, needs_workspace: bool = True
) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        if name in REGISTRY:
            raise ValueError(f"duplicate command: {name}")
        REGISTRY[name] = Command(name, help, params, fn, needs_workspace)
        return fn

    return register
