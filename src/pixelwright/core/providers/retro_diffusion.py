"""`retro-diffusion`: pixel-native generation with palette input (Retro Diffusion API v2).

Docs: https://github.com/Retro-Diffusion/api-examples and the hosted API guide. Requests are
asynchronous: POST returns a task id, then the task is polled until it succeeds or fails.
Outputs belong to the user and may be used commercially (Retro Diffusion FAQ).
"""

from __future__ import annotations

import base64
import time
from collections.abc import Callable
from typing import Any

from pixelwright.core.providers.base import Capabilities, Cost, GenRequest, GenResult, ProviderError
from pixelwright.core.providers.http import HttpRequest, Transport, send, urllib_transport
from pixelwright.core.providers.registry import register
from pixelwright.core.providers.util import b64_png, call_json, palette_png_b64, poll

DEFAULT_URL = "https://api.retrodiffusion.ai"
DEFAULT_STYLE = "rd_core__default"
PRICES = {"rd_fast": 0.03, "rd_core": 0.10, "rd_pro": 0.18}
INPAINT_PRICE = 0.18  # the docs say 0.12 or 0.18; estimate high


class RetroDiffusionProvider:
    name = "retro-diffusion"
    needs_key = True
    capabilities = Capabilities(
        modes=("txt2img", "img2img", "inpaint"),
        n_references=9,
        style_refs=True,
        palette_input=True,
        max_size=(512, 512),
        max_n=4,
        price_per_image=PRICES["rd_core"],
        licence_note="outputs owned by the user; commercial use allowed (Retro Diffusion FAQ)",
    )

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_URL,
        prompt_style: str = DEFAULT_STYLE,
        transport: Transport = urllib_transport,
        poll_s: float = 2.0,
        timeout_s: float = 600.0,
        sleep: Callable[[float], None] = time.sleep,
        **_: Any,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.prompt_style = prompt_style
        self.transport = transport
        self.poll_s = poll_s
        self.timeout_s = timeout_s
        self.sleep = sleep

    def _style(self, req: GenRequest) -> str:
        return str(req.params.get("prompt_style", self.prompt_style))

    def estimate(self, req: GenRequest) -> Cost:
        if req.mode == "inpaint":
            return Cost(INPAINT_PRICE, 1)
        style = self._style(req)
        price = next((p for k, p in PRICES.items() if style.startswith(k)), PRICES["rd_core"])
        return Cost(price * req.n, req.n)

    def _json(self, method: str, path: str, body: Any = None) -> dict[str, Any]:
        answer = call_json(
            self.transport, method, self.base_url + path, {"X-RD-Token": self.api_key}, body
        )
        return dict(answer or {})

    def body(self, req: GenRequest) -> dict[str, Any]:
        if req.mode == "inpaint":
            assert req.init_image is not None and req.mask is not None
            body: dict[str, Any] = {
                "prompt": req.prompt,
                "input_image": b64_png(req.init_image),
                "mask_image": b64_png(req.mask, "L"),
            }
        else:
            body = {
                "prompt": req.prompt,
                "prompt_style": self._style(req),
                "width": req.size[0],
                "height": req.size[1],
                "num_images": req.n,
            }
            if req.init_image is not None:
                body["input_image"] = b64_png(req.init_image)
                body["strength"] = float(req.params.get("strength", 0.75))
            if req.references:
                body["reference_images"] = [b64_png(p) for p in req.references]
            if req.palette:
                body["input_palette"] = palette_png_b64(req.palette)
        if req.seed is not None:
            body["seed"] = req.seed
        return body

    def generate(self, req: GenRequest) -> GenResult:
        inpaint = req.mode == "inpaint"
        submit = "/v2/edit/tools/inpainting/tasks" if inpaint else "/v2/inferences"
        task_path = "/v2/edit/tasks/" if inpaint else "/v2/inferences/tasks/"
        first = self._json("POST", submit, self.body(req))
        if "task_id" in first and "result" not in first:
            task_id = str(first["task_id"])
            first = poll(
                lambda: self._json("GET", task_path + task_id),
                lambda a: a.get("status") in ("succeeded", "failed"),
                what=f"retro-diffusion task {task_id}",
                every_s=self.poll_s,
                timeout_s=self.timeout_s,
                sleep=self.sleep,
            )
        if first.get("status") == "failed":
            raise ProviderError(
                "provider_error", f"retro-diffusion: {first.get('error', 'task failed')}"
            )
        result = dict(first.get("result", first))
        images = [base64.b64decode(b) for b in result.get("base64_images", [])]
        for url in result.get("output_urls", []) if not images else []:
            images.append(send(self.transport, HttpRequest("GET", str(url))).body)
        if not images:
            raise ProviderError("provider_error", "retro-diffusion: answer has no images")
        cost = float(result.get("balance_cost", self.estimate(req).usd))
        raw = {k: v for k, v in result.items() if k not in ("base64_images", "output_urls")}
        return GenResult(
            images, raw, Cost(cost, len(images)), str(result.get("model", "")), req.seed
        )


register("retro-diffusion", RetroDiffusionProvider)
