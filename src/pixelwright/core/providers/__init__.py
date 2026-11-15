"""Image providers (spec §2.9, §5): one contract, one adapter module per provider."""

from pixelwright.core.providers import comfyui as _comfyui  # noqa: F401  (registers it)
from pixelwright.core.providers.base import (
    MODES,
    Capabilities,
    Cost,
    GenRequest,
    GenResult,
    Provider,
    ProviderError,
    check_capability,
    request_hash,
)
from pixelwright.core.providers.cache import Cache
from pixelwright.core.providers.registry import get, names, register
from pixelwright.core.providers.run import run

__all__ = [
    "MODES",
    "Cache",
    "Capabilities",
    "Cost",
    "GenRequest",
    "GenResult",
    "Provider",
    "ProviderError",
    "check_capability",
    "get",
    "names",
    "register",
    "request_hash",
    "run",
]
