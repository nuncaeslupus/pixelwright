"""PixelLab adapter against recorded responses."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from PIL import Image as PILImage

from pixelwright.core import providers as pv
from pixelwright.core.providers.http import HttpRequest, HttpResponse
from pixelwright.core.providers.pixellab import PixelLabProvider

OUT = b"\x89PNG pixellab"


class Recorded:
    def __init__(self) -> None:
        self.calls: list[HttpRequest] = []

    def __call__(self, req: HttpRequest, timeout: float) -> HttpResponse:
        self.calls.append(req)
        b64 = "data:image/png;base64," + base64.b64encode(OUT).decode()
        body = {"image": {"type": "base64", "base64": b64}, "usage": {"type": "usd", "usd": 0.01}}
        return HttpResponse(200, json.dumps(body).encode())


def test_pixellab_inpaint_sends_mask(tmp_path: Path) -> None:
    img = tmp_path / "i.png"
    PILImage.new("RGB", (64, 64)).save(img)
    rec = Recorded()
    prov = PixelLabProvider("pl-secret", transport=rec)
    req = pv.GenRequest(
        "inpaint",
        "door",
        (64, 64),
        init_image=img,
        mask=img,
        n=2,
        seed=1,
        palette=("#112233", "#445566"),
    )
    res = pv.run(prov, req)
    call = rec.calls[0]
    body = json.loads(call.body or b"")
    assert call.url.endswith("/create-image-bitforge")
    assert call.headers["Authorization"] == "Bearer pl-secret"
    assert body["mask_image"]["type"] == "base64" and "inpainting_image" in body
    assert "color_image" in body and json.loads(rec.calls[1].body or b"")["seed"] == 2
    assert res.images == [OUT, OUT] and res.cost.usd == pytest.approx(0.02)


def test_pixellab_txt2img_uses_pixflux() -> None:
    rec = Recorded()
    pv.run(PixelLabProvider("k", transport=rec), pv.GenRequest("txt2img", "x", (160, 90)))
    body = json.loads(rec.calls[0].body or b"")
    assert rec.calls[0].url.endswith("/create-image-pixflux")
    assert body["image_size"] == {"width": 160, "height": 90}


def test_pixellab_refuses_area_over_limit_before_sending(tmp_path: Path) -> None:
    img = tmp_path / "i.png"
    PILImage.new("RGB", (8, 8)).save(img)
    rec = Recorded()
    req = pv.GenRequest("inpaint", "x", (300, 200), init_image=img, mask=img)
    with pytest.raises(pv.ProviderError, match="area limit"):
        pv.run(PixelLabProvider("k", transport=rec), req)
    assert rec.calls == []
