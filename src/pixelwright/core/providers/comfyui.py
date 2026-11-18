"""`comfyui`: the local route (spec D-12). Talks to a ComfyUI server over its HTTP API.

A preset is a ComfyUI workflow in API format plus a map from request fields to node
inputs (`presets/comfyui/<name>.json`, package data, editable). The adapter uploads the
init image and mask, queues the workflow, polls `/history` and fetches the images.
"""

from __future__ import annotations

import copy
import json
import time
import uuid
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from pixelwright.core.providers.base import (
    EXIT_USAGE,
    Capabilities,
    Cost,
    GenRequest,
    GenResult,
    ProviderError,
)
from pixelwright.core.providers.http import HttpRequest, Transport, send, urllib_transport
from pixelwright.core.providers.registry import register

DEFAULT_URL = "http://127.0.0.1:8188"
DEFAULT_PRESET = "sdxl"
PRESET_PACKAGE = "pixelwright.core.providers.presets.comfyui"


def preset_names() -> list[str]:
    files = resources.files(PRESET_PACKAGE).iterdir()
    return sorted(f.name.removesuffix(".json") for f in files if f.name.endswith(".json"))


def load_preset(name: str) -> dict[str, Any]:
    path = resources.files(PRESET_PACKAGE) / f"{name}.json"
    if not path.is_file():
        raise ProviderError(
            "unknown_preset",
            f"comfyui: no preset {name!r}; known: {', '.join(preset_names())}",
            exit_code=EXIT_USAGE,
        )
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _set(workflow: dict[str, Any], target: list[str], value: Any) -> None:
    node, field = target
    workflow[node]["inputs"][field] = value


def _multipart(field: str, filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; '
        f'filename="{filename}"\r\nContent-Type: image/png\r\n\r\n'
    ).encode()
    tail = (
        f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue'
        f"\r\n--{boundary}--\r\n"
    ).encode()
    return head + data + tail, f"multipart/form-data; boundary={boundary}"


class ComfyUIProvider:
    name = "comfyui"
    capabilities = Capabilities(
        modes=("txt2img", "img2img", "inpaint"),
        n_references=0,
        palette_input=False,
        max_size=(2048, 2048),
        max_n=4,
        price_per_image=0.0,
        licence_note="local; the output licence follows the checkpoint and LoRA licences",
    )

    def __init__(
        self,
        base_url: str = DEFAULT_URL,
        preset: str = DEFAULT_PRESET,
        transport: Transport = urllib_transport,
        poll_s: float = 1.0,
        timeout_s: float = 900.0,
        sleep: Callable[[float], None] = time.sleep,
        **_: Any,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.preset = preset
        self.transport = transport
        self.poll_s = poll_s
        self.timeout_s = timeout_s
        self.sleep = sleep

    def estimate(self, req: GenRequest) -> Cost:
        return Cost(0.0, req.n)

    # -- HTTP -----------------------------------------------------------------
    def _url(self, path: str) -> str:
        return self.base_url + path

    def _json(self, method: str, path: str, body: Any = None) -> Any:
        data = None if body is None else json.dumps(body).encode()
        headers = {} if data is None else {"Content-Type": "application/json"}
        try:
            resp = send(self.transport, HttpRequest(method, self._url(path), headers, data))
        except ProviderError as err:
            if err.code == "provider_unavailable":
                err.message = (
                    f"ComfyUI is not answering at {self.base_url}: start it (e.g. "
                    "`python main.py` in the ComfyUI folder) or set [providers.comfyui] "
                    "base_url in pixelwright.toml; `pw doctor` checks it"
                )
                err.args = (err.message,)
            raise
        return json.loads(resp.body or b"null")

    def _upload(self, path: Path) -> str:
        body, ctype = _multipart("image", path.name, path.read_bytes())
        req = HttpRequest("POST", self._url("/upload/image"), {"Content-Type": ctype}, body)
        answer = json.loads(send(self.transport, req).body)
        name = str(answer["name"])
        return f"{answer['subfolder']}/{name}" if answer.get("subfolder") else name

    # -- workflow ---------------------------------------------------------------
    def build(self, req: GenRequest, uploads: dict[str, str]) -> dict[str, Any]:
        preset = load_preset(req.params.get("preset", self.preset))
        mode = preset["modes"].get(req.mode)
        if mode is None:
            raise ProviderError(
                "capability_missing",
                f"comfyui preset {preset['name']} has no {req.mode} workflow",
                exit_code=EXIT_USAGE,
            )
        min_side = int(preset.get("min_side", 0))
        if req.mode != "inpaint" and max(req.size) < min_side:  # inpaint keeps the image size
            raise ProviderError(
                "invalid_size",
                f"comfyui preset {preset['name']} composes badly below {min_side} px on the long "
                f"side (asked {req.size[0]}x{req.size[1]}): use --size 1024x576 for 16:9",
                exit_code=EXIT_USAGE,
            )
        workflow: dict[str, Any] = copy.deepcopy(mode["workflow"])
        values: dict[str, Any] = {**preset.get("defaults", {}), **req.params}
        values.update(
            prompt=req.prompt,
            negative=req.negative,
            width=req.size[0],
            height=req.size[1],
            batch=req.n,
            seed=req.seed if req.seed is not None else 0,
            **uploads,
        )
        for key, target in mode["inputs"].items():
            if key in values:
                _set(workflow, target, values[key])
        if values.get("lora") and "lora" not in mode["inputs"]:
            _add_lora(workflow, str(values["lora"]), float(values.get("lora_strength", 0.8)))
        return workflow

    def generate(self, req: GenRequest) -> GenResult:
        uploads: dict[str, str] = {}
        if req.init_image is not None:
            uploads["init_image"] = self._upload(Path(req.init_image))
        if req.mask is not None:
            uploads["mask"] = self._upload(Path(req.mask))
        workflow = self.build(req, uploads)
        queued = self._json("POST", "/prompt", {"prompt": workflow, "client_id": "pixelwright"})
        prompt_id = str(queued["prompt_id"])
        entry = self._wait(prompt_id)
        images = []
        for output in entry.get("outputs", {}).values():
            for img in output.get("images", []):
                if img.get("type", "output") != "output":
                    continue
                query = urlencode(
                    {
                        "filename": img["filename"],
                        "subfolder": img.get("subfolder", ""),
                        "type": "output",
                    }
                )
                images.append(
                    send(self.transport, HttpRequest("GET", self._url(f"/view?{query}"))).body
                )
        if not images:
            raise ProviderError("provider_error", f"comfyui: prompt {prompt_id} gave no images")
        return GenResult(
            images=images[: req.n],
            raw={"prompt_id": prompt_id, "preset": req.params.get("preset", self.preset)},
            cost=Cost(0.0, len(images[: req.n])),
            model=str(req.params.get("ckpt", "")) or f"comfyui:{self.preset}",
            seed=req.seed,
        )

    def _wait(self, prompt_id: str) -> dict[str, Any]:
        waited = 0.0
        while True:
            history = self._json("GET", f"/history/{prompt_id}") or {}
            entry = history.get(prompt_id)
            if entry:
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise ProviderError(
                        "provider_error",
                        f"comfyui: prompt {prompt_id} failed",
                        details={"messages": status.get("messages", [])[-3:]},
                    )
                if status.get("completed", True):
                    return dict(entry)
            if waited >= self.timeout_s:
                raise ProviderError("provider_error", f"comfyui: prompt {prompt_id} timed out")
            self.sleep(self.poll_s)
            waited += self.poll_s


register("comfyui", ComfyUIProvider)


def _add_lora(workflow: dict[str, Any], name: str, strength: float) -> None:
    """Put a model-only LoRA between the model loader and every node that samples with it."""
    users = [n["inputs"] for n in workflow.values() if isinstance(n["inputs"].get("model"), list)]
    if not users:
        raise ProviderError(
            "capability_missing", "this workflow has no model input to add a LoRA to"
        )
    source = users[0]["model"]
    workflow["lora"] = {
        "class_type": "LoraLoaderModelOnly",
        "inputs": {"lora_name": name, "strength_model": strength, "model": source},
    }
    for inputs in users:
        if inputs["model"] == source:
            inputs["model"] = ["lora", 0]
