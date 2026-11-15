"""GPT Image adapter against recorded responses."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage

from pixelwright.core import providers as pv
from pixelwright.core.providers.gpt_image import GptImageProvider, api_size, openai_mask
from pixelwright.core.providers.http import HttpRequest, HttpResponse

OUT = b"\x89PNG gpt"


class Recorded:
    def __init__(self) -> None:
        self.calls: list[HttpRequest] = []

    def __call__(self, req: HttpRequest, timeout: float) -> HttpResponse:
        self.calls.append(req)
        data = [{"b64_json": base64.b64encode(OUT).decode()}] * 2
        return HttpResponse(200, json.dumps({"data": data, "usage": {"total_tokens": 9}}).encode())


def _mask(path: Path) -> None:
    arr = np.zeros((8, 8), dtype=np.uint8)
    arr[2:4, 2:4] = 255
    PILImage.fromarray(arr, "L").save(path)


def test_gpt_image_edit_sends_mask_and_parses_b64(tmp_path: Path) -> None:
    img, mask = tmp_path / "i.png", tmp_path / "m.png"
    PILImage.new("RGB", (8, 8)).save(img)
    _mask(mask)
    rec = Recorded()
    prov = GptImageProvider("sk-secret", transport=rec)
    res = pv.run(prov, pv.GenRequest("inpaint", "door", (8, 8), init_image=img, mask=mask, n=2))
    call = rec.calls[0]
    assert (
        call.url.endswith("/images/edits") and call.headers["Authorization"] == "Bearer sk-secret"
    )
    body = call.body or b""
    assert b'name="mask"' in body and b'name="image[]"' in body and b"gpt-image-1" in body
    assert res.images == [OUT, OUT] and res.cost.usd == pytest.approx(0.084)
    assert "sk-secret" not in json.dumps(res.raw)


def test_gpt_image_txt2img_uses_generations_json() -> None:
    rec = Recorded()
    pv.run(GptImageProvider("k", transport=rec), pv.GenRequest("txt2img", "x", (640, 360)))
    body = json.loads(rec.calls[0].body or b"")
    assert rec.calls[0].url.endswith("/images/generations")
    assert body["size"] == "1536x1024" and body["quality"] == "medium" and body["n"] == 1


def test_openai_mask_is_transparent_where_to_paint(tmp_path: Path) -> None:
    _mask(tmp_path / "m.png")
    with PILImage.open(io.BytesIO(openai_mask(tmp_path / "m.png"))) as im:
        alpha = np.asarray(im)[..., 3]
    assert alpha[2, 2] == 0 and alpha[0, 0] == 255


def test_api_size_by_aspect() -> None:
    assert api_size((48, 80)) == "1024x1536" and api_size((16, 16)) == "1024x1024"
