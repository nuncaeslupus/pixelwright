"""Providers by name. Adapters register a factory; nothing is built until asked for."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pixelwright.core.providers.base import EXIT_USAGE, Provider, ProviderError

Factory = Callable[..., Provider]
_FACTORIES: dict[str, Factory] = {}


def register(name: str, factory: Factory) -> None:
    _FACTORIES[name] = factory


def names() -> list[str]:
    return sorted(_FACTORIES)


def get(name: str, **config: Any) -> Provider:
    try:
        factory = _FACTORIES[name]
    except KeyError:
        raise ProviderError(
            "unknown_provider",
            f"unknown provider {name!r}; known: {', '.join(names()) or 'none'}",
            exit_code=EXIT_USAGE,
        ) from None
    return factory(**config)


def needs_key(name: str) -> bool:
    """Whether the provider's factory takes an `api_key` (paid, remote providers)."""
    return bool(getattr(_FACTORIES.get(name), "needs_key", False))
