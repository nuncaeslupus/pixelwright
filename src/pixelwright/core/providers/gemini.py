"""`gemini`: Gemini image models as a painter (references and edits, no mask or palette).

Uses the REST `generateContent` endpoint (`responseModalities: ["IMAGE"]`), one call per
candidate. The default model is `gemini-2.5-flash-image`; Google now documents newer image
models on the Interactions API, so the model id is configurable (`[providers.gemini] model`)
and the real-call check in the owner's local test prompt confirms it. Outputs carry an
invisible SynthID watermark.
"""

from __future__ import annotations

import base64
from math import gcd
from typing import Any

from pixelwright.core.providers.base import Capabilities, Cost, GenRequest, GenResult, ProviderError
from pixelwright.core.providers.http import Transport, urllib_transport
from pixelwright.core.providers.registry import register
from pixelwright.core.providers.util import b64_png, call_json

DEFAULT_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-2.5-flash-image"
PRICE = 0.039  # USD per image up to 1024x1024 (Gemini API pricing page)
ASPECTS = ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")


def aspect_ratio(size: tuple[int, int]) -> str:
    """The supported aspect ratio closest to `size`."""
    w, h = size
    g = gcd(w, h)
    exact = f"{w // g}:{h // g}"
    if exact in ASPECTS:
        return exact
    target = w / h
    return min(ASPECTS, key=lambda a: abs(int(a.split(":")[0]) / int(a.split(":")[1]) - target))


class GeminiProvider:
    name = "gemini"
    needs_key = True
    capabilities = Capabilities(
        modes=("txt2img", "img2img", "edit"),
        n_references=3,
        style_refs=True,
        palette_input=False,
        max_size=(1024, 1024),
        max_n=4,
        price_per_image=PRICE,
        watermark=True,
        licence_note="Gemini API terms; SynthID watermark; check commercial use before shipping",
    )

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_URL,
        model: str = DEFAULT_MODEL,
        transport: Transport = urllib_transport,
        **_: Any,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.transport = transport

    def estimate(self, req: GenRequest) -> Cost:
        return Cost(PRICE * req.n, req.n)

    def body(self, req: GenRequest) -> dict[str, Any]:
        parts: list[dict[str, Any]] = [{"text": req.prompt}]
        if req.negative:
            parts.append({"text": f"Avoid: {req.negative}"})
        for path in ([req.init_image] if req.init_image is not None else []) + list(req.references):
            parts.append({"inline_data": {"mime_type": "image/png", "data": b64_png(path)}})
        config: dict[str, Any] = {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": aspect_ratio(req.size)},
        }
        if req.seed is not None:
            config["seed"] = req.seed
        return {"contents": [{"role": "user", "parts": parts}], "generationConfig": config}

    def generate(self, req: GenRequest) -> GenResult:
        url = f"{self.base_url}/models/{self.model}:generateContent"
        body = self.body(req)
        images: list[bytes] = []
        usage: list[Any] = []
        for i in range(req.n):
            if req.seed is not None:
                body["generationConfig"]["seed"] = req.seed + i
            answer = call_json(self.transport, "POST", url, {"x-goog-api-key": self.api_key}, body)
            found = [
                p.get("inlineData") or p.get("inline_data")
                for c in answer.get("candidates", [])
                for p in c.get("content", {}).get("parts", [])
            ]
            data = [d["data"] for d in found if d and d.get("data")]
            if not data:
                reason = answer.get("promptFeedback", {}).get("blockReason") or "no image returned"
                raise ProviderError("provider_error", f"gemini: {reason}")
            images.append(base64.b64decode(data[0]))
            usage.append(answer.get("usageMetadata", {}))
        raw = {"model": self.model, "usage": usage}
        return GenResult(images, raw, Cost(PRICE * len(images), len(images)), self.model, req.seed)


register("gemini", GeminiProvider)
