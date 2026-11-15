"""Run one request: capability check, cache lookup, optional guard, call, cache write."""

from __future__ import annotations

from collections.abc import Callable

from pixelwright.core.providers.base import (
    GenRequest,
    GenResult,
    Provider,
    check_capability,
    request_hash,
)
from pixelwright.core.providers.cache import Cache

# Called with (provider, request, estimated cost in USD) before a non-cached call; raise to stop.
Guard = Callable[[Provider, GenRequest, float], None]


def run(
    provider: Provider,
    req: GenRequest,
    cache: Cache | None = None,
    guard: Guard | None = None,
) -> GenResult:
    check_capability(provider, req)
    key = request_hash(provider.name, req)
    if cache is not None:
        hit = cache.get(key)
        if hit is not None:
            return hit
    if guard is not None:
        guard(provider, req, provider.estimate(req).usd)
    result = provider.generate(req)
    result.request_hash = key
    result.cache_hit = False
    if cache is not None:
        cache.put(key, req.canonical(), result)
    return result
