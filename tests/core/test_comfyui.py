"""ComfyUI adapter against recorded responses (no server, no network)."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from pixelwright.core import providers as pv
from pixelwright.core.providers.base import ProviderError
from pixelwright.core.providers.comfyui import ComfyUIProvider, load_preset, preset_names
from pixelwright.core.providers.http import HttpRequest, HttpResponse

PNG = b"\x89PNG recorded"


class Recorded:
    """Answers like ComfyUI: upload, queue, history (pending once, then done), view."""

    def __init__(self, status: str = "success") -> None:
        self.calls: list[HttpRequest] = []
        self.history_polls = 0
        self.status = status

    def __call__(self, req: HttpRequest, timeout: float) -> HttpResponse:
        self.calls.append(req)
        path = urlparse(req.url).path
        if path == "/upload/image":
            return HttpResponse(200, b'{"name": "init.png", "subfolder": "", "type": "input"}')
        if path == "/prompt":
            return HttpResponse(200, b'{"prompt_id": "p1", "number": 1}')
        if path == "/history/p1":
            self.history_polls += 1
            if self.history_polls == 1:
                return HttpResponse(200, b"{}")
            entry = {
                "outputs": {
                    "9": {
                        "images": [
                            {"filename": "pw_0.png", "subfolder": "", "type": "output"},
                            {"filename": "pw_1.png", "subfolder": "", "type": "output"},
                        ]
                    }
                },
                "status": {
                    "status_str": self.status,
                    "completed": self.status == "success",
                    "messages": [["execution_error", {"exception_message": "oom"}]],
                },
            }
            return HttpResponse(200, json.dumps({"p1": entry}).encode())
        if path == "/view":
            name = parse_qs(urlparse(req.url).query)["filename"][0]
            return HttpResponse(200, PNG + name.encode())
        return HttpResponse(404, b"")


def _prov(rec: Recorded) -> ComfyUIProvider:
    return ComfyUIProvider(transport=rec, sleep=lambda s: None)


def test_comfyui_img2img_replays_recorded_history(tmp_path: Path) -> None:
    init = tmp_path / "sketch.png"
    init.write_bytes(b"sketch")
    rec = Recorded()
    req = pv.GenRequest("img2img", "house on a hill", (1024, 576), init_image=init, n=2, seed=5)
    res = pv.run(_prov(rec), req)
    assert res.images == [PNG + b"pw_0.png", PNG + b"pw_1.png"] and res.cost.usd == 0.0
    queued = json.loads(next(c for c in rec.calls if c.url.endswith("/prompt")).body or b"")
    wf = queued["prompt"]
    assert wf["11"]["inputs"]["image"] == "init.png"
    assert wf["6"]["inputs"]["text"] == "house on a hill"
    assert wf["3"]["inputs"]["seed"] == 5 and wf["5"]["inputs"]["amount"] == 2
    assert wf["3"]["inputs"]["denoise"] == 0.75 and rec.history_polls == 2


def test_comfyui_txt2img_sets_size_and_params() -> None:
    prov = ComfyUIProvider(transport=Recorded())
    req = pv.GenRequest(
        "txt2img", "x", (1024, 576), params={"lora": "mine.safetensors", "steps": 12}
    )
    wf = prov.build(req, {})
    assert (wf["5"]["inputs"]["width"], wf["5"]["inputs"]["height"]) == (1024, 576)
    assert (
        wf["10"]["inputs"]["lora_name"] == "mine.safetensors" and wf["3"]["inputs"]["steps"] == 12
    )


def test_comfyui_inpaint_uploads_mask(tmp_path: Path) -> None:
    img = tmp_path / "i.png"
    img.write_bytes(b"i")
    wf = ComfyUIProvider(transport=Recorded()).build(
        pv.GenRequest("inpaint", "x", (1024, 576), init_image=img, mask=img),
        {"init_image": "i.png", "mask": "m.png"},
    )
    assert wf["13"]["inputs"]["image"] == "m.png" and wf["12"]["inputs"]["mask"] == ["13", 0]


def test_comfyui_error_status_is_provider_error(tmp_path: Path) -> None:
    with pytest.raises(pv.ProviderError) as e:
        pv.run(_prov(Recorded(status="error")), pv.GenRequest("txt2img", "x", (1024, 576)))
    assert e.value.code == "provider_error" and e.value.exit_code == 5


def test_comfyui_down_says_how_to_fix() -> None:
    def down(req: HttpRequest, timeout: float) -> HttpResponse:
        raise pv.ProviderError("provider_unavailable", "refused")

    with pytest.raises(pv.ProviderError, match="pw doctor"):
        pv.run(ComfyUIProvider(transport=down), pv.GenRequest("txt2img", "x", (1024, 576)))


def test_presets_are_valid_workflow_json() -> None:
    assert "sdxl" in preset_names()
    for name in preset_names():
        preset = load_preset(name)
        for mode, spec in preset["modes"].items():
            assert mode in pv.MODES
            for target in spec["inputs"].values():
                node, field = target
                assert field in spec["workflow"][node]["inputs"], (name, mode, target)


def test_registry_builds_comfyui_with_config() -> None:
    prov = pv.get("comfyui", base_url="http://gpu-box:8188/")
    assert isinstance(prov, ComfyUIProvider) and prov.base_url == "http://gpu-box:8188"


def test_controlnet_workflow_carries_sketch(tmp_path: Path) -> None:
    sketch = tmp_path / "layout.png"
    sketch.write_bytes(b"layout")
    rec = Recorded()
    req = pv.GenRequest(
        "img2img", "a crypt", (1024, 576), init_image=sketch, seed=3,
        params={"preset": "sdxl-controlnet", "control_strength": 0.5},
    )  # fmt: skip
    pv.run(_prov(rec), req)
    wf = json.loads(next(c for c in rec.calls if c.url.endswith("/prompt")).body or b"")["prompt"]
    assert wf["11"]["inputs"]["image"] == "init.png"  # the uploaded sketch ...
    assert wf["13"]["inputs"]["image"] == ["11", 0]  # ... goes through edges ...
    apply = wf["15"]["inputs"]
    assert apply["image"] == ["13", 0] and apply["strength"] == 0.5  # ... into ControlNet
    assert wf["3"]["inputs"]["positive"] == ["15", 0] and wf["3"]["inputs"]["denoise"] == 1.0
    assert (wf["5"]["inputs"]["width"], wf["5"]["inputs"]["height"]) == (1024, 576)


def test_img2img_scales_the_init_image_to_the_request_size(tmp_path: Path) -> None:
    init = tmp_path / "sketch.png"
    init.write_bytes(b"s")
    for preset in ("sdxl", "flux-schnell"):
        req = pv.GenRequest("img2img", "x", (1024, 576), init_image=init, params={"preset": preset})
        wf = ComfyUIProvider(transport=Recorded()).build(req, {"init_image": "sketch.png"})
        scale = wf["20"]["inputs"]
        assert (scale["width"], scale["height"]) == (1024, 576)
        enc = next(v for v in wf.values() if v["class_type"] == "VAEEncode")
        assert enc["inputs"]["pixels"] == ["20", 0], preset  # the latent is not 40x22 any more


def test_small_sizes_are_refused_with_the_fix() -> None:
    with pytest.raises(ProviderError) as e:
        ComfyUIProvider(transport=Recorded()).build(pv.GenRequest("txt2img", "x", (640, 360)), {})
    assert e.value.code == "invalid_size" and "1024x576" in e.value.message


def test_inpaint_is_not_refused_for_a_small_sprite(tmp_path: Path) -> None:
    img = tmp_path / "s.png"
    img.write_bytes(b"s")
    req = pv.GenRequest("inpaint", "x", (256, 256), init_image=img, mask=img)
    assert ComfyUIProvider(transport=Recorded()).build(req, {"init_image": "s.png"})
