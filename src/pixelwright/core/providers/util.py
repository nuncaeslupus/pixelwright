"""Helpers shared by the remote adapters: base64 images, palette swatches, JSON calls, polling."""

from __future__ import annotations

import base64
import io
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image as PILImage

from pixelwright.core.providers.base import ProviderError
from pixelwright.core.providers.http import HttpRequest, Transport, send


def b64_png(path: Path, mode: str = "RGB") -> str:
    """The image at `path` as base64 PNG (no `data:` prefix), converted to `mode`."""
    with PILImage.open(path) as im:
        buf = io.BytesIO()
        im.convert(mode).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def palette_png_b64(colors: tuple[str, ...]) -> str:
    """A 1-pixel-high swatch with one pixel per palette color, as base64 PNG."""
    im = PILImage.new("RGB", (len(colors), 1))
    for x, hexcolor in enumerate(colors):
        h = hexcolor.lstrip("#")
        im.putpixel((x, 0), (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def call_json(
    transport: Transport, method: str, url: str, headers: dict[str, str], body: Any = None
) -> Any:
    data = None if body is None else json.dumps(body).encode()
    hdrs = {"Accept": "application/json", **headers}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    resp = send(transport, HttpRequest(method, url, hdrs, data))
    try:
        return json.loads(resp.body or b"null")
    except json.JSONDecodeError as err:
        raise ProviderError("provider_error", f"{url}: answer is not JSON") from err


def poll(
    fetch: Callable[[], dict[str, Any]],
    done: Callable[[dict[str, Any]], bool],
    *,
    what: str,
    every_s: float = 2.0,
    timeout_s: float = 600.0,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Call `fetch` until `done(answer)`; raise `provider_error` on timeout."""
    waited = 0.0
    while True:
        answer = fetch()
        if done(answer):
            return answer
        if waited >= timeout_s:
            raise ProviderError("provider_error", f"{what} timed out after {timeout_s:.0f} s")
        sleep(every_s)
        waited += every_s
