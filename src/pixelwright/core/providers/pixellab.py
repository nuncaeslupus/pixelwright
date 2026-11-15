"""`pixellab`: pixel-native generation (PixelLab API v2) with forced palette and inpainting.

Endpoints (from the v2 OpenAPI paths): `POST /create-image-pixflux` (init image, forced
palette; area up to 400x400) and `POST /create-image-bitforge` (style image, inpainting;
area up to 200x200). Both answer `{"image": {"type": "base64", "base64": "data:..."},
"usage": {"type": "usd", "usd": ...}}`. The request field names follow PixelLab's Python
client and are not in the published schema, so the owner's local test prompt checks them
with one real call before the benchmark; fix them here if PixelLab answers 422.
"""

from __future__ import annotations

import base64
from typing import Any

from pixelwright.core.providers.base import Capabilities, Cost, GenRequest, GenResult, ProviderError
from pixelwright.core.providers.http import Transport, urllib_transport
from pixelwright.core.providers.registry import register
from pixelwright.core.providers.util import b64_png, call_json, palette_png_b64

DEFAULT_URL = "https://api.pixellab.ai/v2"
PRICE_ESTIMATE = 0.02  # USD per image; the real price comes back in `usage.usd`
PIXFLUX_MAX_AREA = 400 * 400
BITFORGE_MAX_AREA = 200 * 200


def _image(b64: str) -> dict[str, str]:
    return {"type": "base64", "base64": b64}


class PixelLabProvider:
    name = "pixellab"
    needs_key = True
    capabilities = Capabilities(
        modes=("txt2img", "img2img", "inpaint"),
        n_references=1,
        style_refs=True,
        palette_input=True,
        max_size=(400, 400),
        max_n=4,
        price_per_image=PRICE_ESTIMATE,
        licence_note="PixelLab terms: check commercial use for the plan in use",
    )

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_URL,
        transport: Transport = urllib_transport,
        **_: Any,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.transport = transport

    def estimate(self, req: GenRequest) -> Cost:
        return Cost(PRICE_ESTIMATE * req.n, req.n)

    def endpoint(self, req: GenRequest) -> str:
        bitforge = req.mode == "inpaint" or bool(req.references)
        w, h = req.size
        limit = BITFORGE_MAX_AREA if bitforge else PIXFLUX_MAX_AREA
        if w * h > limit:
            raise ProviderError(
                "capability_missing",
                f"pixellab: {w}x{h} is over the {'bitforge' if bitforge else 'pixflux'} "
                f"area limit ({limit} px); generate at native size",
                exit_code=2,
            )
        return "/create-image-bitforge" if bitforge else "/create-image-pixflux"

    def body(self, req: GenRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "description": req.prompt,
            "image_size": {"width": req.size[0], "height": req.size[1]},
            "no_background": bool(req.params.get("no_background", False)),
        }
        if req.negative:
            body["negative_description"] = req.negative
        if req.mode == "img2img" and req.init_image is not None:
            body["init_image"] = _image(b64_png(req.init_image, "RGBA"))
            body["init_image_strength"] = int(req.params.get("init_image_strength", 300))
        if req.mode == "inpaint" and req.init_image is not None and req.mask is not None:
            body["inpainting_image"] = _image(b64_png(req.init_image, "RGBA"))
            body["mask_image"] = _image(b64_png(req.mask, "RGB"))
        if req.references:
            body["style_image"] = _image(b64_png(req.references[0], "RGBA"))
        if req.palette:
            body["color_image"] = _image(palette_png_b64(req.palette))
        for key in ("text_guidance_scale", "outline", "shading", "detail", "view", "direction"):
            if key in req.params:
                body[key] = req.params[key]
        return body

    def generate(self, req: GenRequest) -> GenResult:
        url = self.base_url + self.endpoint(req)
        body = self.body(req)
        auth = {"Authorization": f"Bearer {self.api_key}"}
        images, spent = [], 0.0
        for i in range(req.n):
            if req.seed is not None:
                body["seed"] = req.seed + i
            answer = call_json(self.transport, "POST", url, auth, body)
            data = str(answer.get("image", {}).get("base64", ""))
            if not data:
                raise ProviderError("provider_error", "pixellab: answer has no image")
            images.append(base64.b64decode(data.split(",", 1)[-1]))
            spent += float(answer.get("usage", {}).get("usd", PRICE_ESTIMATE))
        raw = {"endpoint": self.endpoint(req), "usd": spent}
        return GenResult(images, raw, Cost(round(spent, 6), len(images)), "pixellab", req.seed)


register("pixellab", PixelLabProvider)
