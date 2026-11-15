"""Retro Diffusion adapter against recorded responses."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from pixelwright.core import providers as pv
from pixelwright.core.providers.http import HttpRequest, HttpResponse
from pixelwright.core.providers.retro_diffusion import RetroDiffusionProvider
from pixelwright.fixtures import tour
from pixelwright.io.png import encode_png

OUT = b"\x89PNG out"


class Recorded:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[HttpRequest] = []
        self.polls = 0
        self.fail = fail

    def __call__(self, req: HttpRequest, timeout: float) -> HttpResponse:
        self.calls.append(req)
        if req.method == "POST":
            return HttpResponse(202, b'{"status": "accepted", "task_id": "t1"}')
        self.polls += 1
        if self.polls == 1:
            return HttpResponse(200, b'{"status": "running"}')
        if self.fail:
            return HttpResponse(200, b'{"status": "failed", "error": "bad prompt"}')
        result = {
            "base64_images": [base64.b64encode(OUT).decode()] * 2,
            "balance_cost": 0.2,
            "model": "rd_core",
            "remaining_balance": 9.8,
        }
        return HttpResponse(200, json.dumps({"status": "succeeded", "result": result}).encode())


def _prov(rec: Recorded) -> RetroDiffusionProvider:
    return RetroDiffusionProvider("rdpk-secret", transport=rec, sleep=lambda s: None)


def test_retro_diffusion_sends_palette_and_strength(tmp_path: Path) -> None:
    init = tmp_path / "s.png"
    init.write_bytes(encode_png(tour.sketch()))
    rec = Recorded()
    req = pv.GenRequest(
        "img2img",
        "house",
        (160, 90),
        init_image=init,
        n=2,
        seed=4,
        palette=("#2b2340", "#f4d58a"),
        params={"strength": 0.5},
    )
    res = pv.run(_prov(rec), req)
    body = json.loads(rec.calls[0].body or b"")
    assert rec.calls[0].url.endswith("/v2/inferences")
    assert rec.calls[0].headers["X-RD-Token"] == "rdpk-secret"
    assert body["strength"] == 0.5 and body["num_images"] == 2 and body["seed"] == 4
    assert base64.b64decode(body["input_palette"]).startswith(b"\x89PNG")
    assert res.images == [OUT, OUT] and res.cost.usd == 0.2 and res.model == "rd_core"
    assert rec.calls[-1].url.endswith("/v2/inferences/tasks/t1")


def test_retro_diffusion_inpaint_uses_edit_tool(tmp_path: Path) -> None:
    img = tmp_path / "i.png"
    img.write_bytes(encode_png(tour.sketch()))
    rec = Recorded()
    req = pv.GenRequest("inpaint", "door", (160, 90), init_image=img, mask=img)
    pv.run(_prov(rec), req)
    assert rec.calls[0].url.endswith("/v2/edit/tools/inpainting/tasks")
    assert "mask_image" in json.loads(rec.calls[0].body or b"")


def test_retro_diffusion_failed_task_is_provider_error() -> None:
    with pytest.raises(pv.ProviderError, match="bad prompt"):
        pv.run(_prov(Recorded(fail=True)), pv.GenRequest("txt2img", "x", (64, 64)))


def test_retro_diffusion_estimate_by_style() -> None:
    prov = _prov(Recorded())
    fast = pv.GenRequest("txt2img", "x", (64, 64), n=2, params={"prompt_style": "rd_fast__x"})
    assert prov.estimate(fast).usd == pytest.approx(0.06)
    assert prov.estimate(pv.GenRequest("txt2img", "x", (64, 64))).usd == pytest.approx(0.10)


def test_retro_diffusion_needs_key() -> None:
    assert RetroDiffusionProvider.needs_key
