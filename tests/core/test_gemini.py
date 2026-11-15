"""Gemini adapter against recorded responses."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from pixelwright.core import providers as pv
from pixelwright.core.providers.gemini import GeminiProvider, aspect_ratio
from pixelwright.core.providers.http import HttpRequest, HttpResponse
from pixelwright.fixtures import tour
from pixelwright.io.png import encode_png

OUT = b"\x89PNG gemini"


class Recorded:
    def __init__(self, blocked: bool = False) -> None:
        self.calls: list[HttpRequest] = []
        self.blocked = blocked

    def __call__(self, req: HttpRequest, timeout: float) -> HttpResponse:
        self.calls.append(req)
        if self.blocked:
            return HttpResponse(200, b'{"promptFeedback": {"blockReason": "SAFETY"}}')
        part = {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(OUT).decode()}}
        body = {
            "candidates": [{"content": {"parts": [{"text": "here"}, part]}}],
            "usageMetadata": {"candidatesTokenCount": 1290},
        }
        return HttpResponse(200, json.dumps(body).encode())


def test_gemini_img2img_sends_references_and_parses_image(tmp_path: Path) -> None:
    init, ref = tmp_path / "s.png", tmp_path / "r.png"
    init.write_bytes(encode_png(tour.sketch()))
    ref.write_bytes(encode_png(tour.painted()))
    rec = Recorded()
    prov = GeminiProvider("k-secret", transport=rec)
    req = pv.GenRequest(
        "img2img", "dusk", (640, 360), init_image=init, references=(ref,), n=2, seed=7
    )
    res = pv.run(prov, req)
    assert res.images == [OUT, OUT] and res.cost.usd == pytest.approx(0.078)
    assert len(rec.calls) == 2 and rec.calls[0].headers["x-goog-api-key"] == "k-secret"
    assert rec.calls[0].url.endswith("/models/gemini-2.5-flash-image:generateContent")
    body = json.loads(rec.calls[1].body or b"")
    parts = body["contents"][0]["parts"]
    assert parts[0]["text"] == "dusk" and len([p for p in parts if "inline_data" in p]) == 2
    assert body["generationConfig"]["imageConfig"]["aspectRatio"] == "16:9"
    assert body["generationConfig"]["seed"] == 8 and "k-secret" not in json.dumps(res.raw)


def test_gemini_blocked_prompt_is_provider_error() -> None:
    prov = GeminiProvider("k", transport=Recorded(blocked=True))
    with pytest.raises(pv.ProviderError, match="SAFETY"):
        pv.run(prov, pv.GenRequest("txt2img", "x", (64, 64)))


def test_gemini_refuses_inpaint_before_sending(tmp_path: Path) -> None:
    img = tmp_path / "i.png"
    img.write_bytes(b"x")
    rec = Recorded()
    with pytest.raises(pv.ProviderError, match="does not support"):
        pv.run(
            GeminiProvider("k", transport=rec),
            pv.GenRequest("inpaint", "x", (64, 64), init_image=img, mask=img),
        )
    assert rec.calls == []


def test_aspect_ratio_picks_nearest() -> None:
    assert aspect_ratio((320, 180)) == "16:9" and aspect_ratio((48, 80)) == "9:16"
    assert aspect_ratio((100, 100)) == "1:1"
