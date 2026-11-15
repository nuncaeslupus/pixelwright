"""One small HTTP client for every adapter: injectable transport, retry on 429/5xx."""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from pixelwright.core.providers.base import ProviderError

RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
RETRIES = 2
BACKOFF_S = 1.0


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes | None = None


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)


class Transport(Protocol):
    def __call__(self, req: HttpRequest, timeout: float) -> HttpResponse: ...


def urllib_transport(req: HttpRequest, timeout: float) -> HttpResponse:
    """The real network transport; tests pass a recorded one instead."""
    r = urllib.request.Request(req.url, data=req.body, headers=req.headers, method=req.method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return HttpResponse(resp.status, resp.read(), dict(resp.headers))
    except urllib.error.HTTPError as e:
        return HttpResponse(e.code, e.read(), dict(e.headers or {}))
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise ProviderError(
            "provider_unavailable", f"cannot reach {req.url}: {e}", details={"url": req.url}
        ) from e


def send(
    transport: Transport,
    req: HttpRequest,
    *,
    timeout: float = 120.0,
    retries: int = RETRIES,
    backoff_s: float = BACKOFF_S,
    sleep: Callable[[float], None] = time.sleep,
) -> HttpResponse:
    """Send with up to `retries` retries on 429/5xx (exponential backoff); raise on failure."""
    resp = transport(req, timeout)
    for attempt in range(retries):
        if resp.status not in RETRY_STATUS:
            break
        sleep(backoff_s * 2**attempt)
        resp = transport(req, timeout)
    if resp.status >= 400:
        raise ProviderError(
            "provider_error",
            f"{req.method} {req.url} returned HTTP {resp.status}",
            details={"status": resp.status, "body": resp.body[:500].decode(errors="replace")},
        )
    return resp
