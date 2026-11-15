"""`gpt-image`: OpenAI GPT Image models (generations, edits with references and a mask).

Endpoints: `POST /v1/images/generations` (JSON) and `POST /v1/images/edits` (multipart;
`image[]` for the init image and references, `mask` where alpha 0 marks the area to paint).
GPT image models always answer with base64 images. No seed. The model is configurable
(`[providers.gpt-image] model`); prices are estimates by quality for a 1024-px image.
"""

from __future__ import annotations

import base64
import io
import json
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image as PILImage

from pixelwright.core.providers.base import Capabilities, Cost, GenRequest, GenResult, ProviderError
from pixelwright.core.providers.http import HttpRequest, Transport, send, urllib_transport
from pixelwright.core.providers.registry import register
from pixelwright.core.providers.util import call_json

DEFAULT_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-image-1"
PRICES = {"low": 0.011, "medium": 0.042, "high": 0.167, "auto": 0.167}  # USD per image
SIZES = ((1024, 1024), (1536, 1024), (1024, 1536))


def api_size(size: tuple[int, int]) -> str:
    """The supported size whose aspect ratio is closest to `size`."""
    target = size[0] / size[1]
    w, h = min(SIZES, key=lambda s: abs(s[0] / s[1] - target))
    return f"{w}x{h}"


def openai_mask(path: Path) -> bytes:
    """pixelwright masks are white where to repaint; OpenAI wants alpha 0 there."""
    with PILImage.open(path) as im:
        region = np.asarray(im.convert("L")) > 127
    rgba = np.zeros((*region.shape, 4), dtype=np.uint8)
    rgba[..., 3] = np.where(region, 0, 255)
    buf = io.BytesIO()
    PILImage.fromarray(rgba, "RGBA").save(buf, format="PNG")
    return buf.getvalue()


def multipart(fields: dict[str, str], files: list[tuple[str, str, bytes]]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    out = io.BytesIO()
    for name, value in fields.items():
        out.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        out.write(value.encode() + b"\r\n")
    for name, filename, data in files:
        out.write(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
            f'filename="{filename}"\r\nContent-Type: image/png\r\n\r\n'.encode()
        )
        out.write(data + b"\r\n")
    out.write(f"--{boundary}--\r\n".encode())
    return out.getvalue(), f"multipart/form-data; boundary={boundary}"


class GptImageProvider:
    name = "gpt-image"
    needs_key = True
    capabilities = Capabilities(
        modes=("txt2img", "img2img", "edit", "inpaint"),
        n_references=15,
        style_refs=True,
        palette_input=False,
        max_size=(1536, 1536),
        max_n=4,
        price_per_image=PRICES["medium"],
        licence_note="OpenAI terms: outputs assigned to the user; check content policy",
    )

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_URL,
        model: str = DEFAULT_MODEL,
        quality: str = "medium",
        transport: Transport = urllib_transport,
        **_: Any,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.quality = quality
        self.transport = transport

    def _quality(self, req: GenRequest) -> str:
        return str(req.params.get("quality", self.quality))

    def estimate(self, req: GenRequest) -> Cost:
        return Cost(PRICES.get(self._quality(req), PRICES["high"]) * req.n, req.n)

    def generate(self, req: GenRequest) -> GenResult:
        auth = {"Authorization": f"Bearer {self.api_key}"}
        common = {
            "model": str(req.params.get("model", self.model)),
            "prompt": req.prompt if not req.negative else f"{req.prompt}\nAvoid: {req.negative}",
            "n": str(req.n),
            "size": str(req.params.get("size", api_size(req.size))),
            "quality": self._quality(req),
        }
        if req.mode == "txt2img":
            body: dict[str, Any] = {**common, "n": req.n, "output_format": "png"}
            answer = call_json(
                self.transport, "POST", f"{self.base_url}/images/generations", auth, body
            )
        else:
            assert req.init_image is not None
            images = [Path(req.init_image), *req.references]
            files = [("image[]", p.name, p.read_bytes()) for p in images]
            if req.mode == "inpaint" and req.mask is not None:
                files.append(("mask", "mask.png", openai_mask(Path(req.mask))))
            data, ctype = multipart(common, files)
            url = f"{self.base_url}/images/edits"
            headers = {**auth, "Content-Type": ctype}
            answer = json.loads(send(self.transport, HttpRequest("POST", url, headers, data)).body)
        found = [d.get("b64_json") for d in answer.get("data", []) if d.get("b64_json")]
        if not found:
            raise ProviderError("provider_error", "gpt-image: answer has no images")
        out = [base64.b64decode(b) for b in found]
        raw = {"model": common["model"], "usage": answer.get("usage", {}), "size": common["size"]}
        return GenResult(out, raw, self.estimate(req), common["model"], None)


register("gpt-image", GptImageProvider)
