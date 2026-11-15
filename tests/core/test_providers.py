"""Provider framework: hashing, cache, capability check, retry, registry."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from pixelwright.core import providers as pv
from pixelwright.core.providers.http import HttpRequest, HttpResponse, send


def _png(color: tuple[int, int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(buf, format="PNG")
    return buf.getvalue()


class FakeProvider:
    name = "fake"
    capabilities = pv.Capabilities(modes=("txt2img", "img2img"), max_n=4, price_per_image=0.04)

    def __init__(self) -> None:
        self.calls = 0

    def estimate(self, req: pv.GenRequest) -> pv.Cost:
        return pv.Cost(self.capabilities.price_per_image * req.n, req.n)

    def generate(self, req: pv.GenRequest) -> pv.GenResult:
        self.calls += 1
        imgs = [_png((10 * i + self.calls, 0, 0)) for i in range(req.n)]
        return pv.GenResult(imgs, {"id": "r1", "api_key": "secret"}, self.estimate(req), "m1", 7)


def test_same_request_twice_is_cache_hit_with_zero_cost(tmp_path: Path) -> None:
    prov, cache = FakeProvider(), pv.Cache(tmp_path / "cache")
    req = pv.GenRequest("txt2img", "a hill", (64, 36), n=2, seed=1)
    first = pv.run(prov, req, cache)
    second = pv.run(prov, req, cache)
    assert prov.calls == 1
    assert not first.cache_hit and second.cache_hit
    assert second.cost.usd == 0.0 and first.cost.usd == pytest.approx(0.08)
    assert second.images == first.images
    assert second.request_hash == first.request_hash


def test_cache_strips_secret_fields(tmp_path: Path) -> None:
    cache = pv.Cache(tmp_path)
    res = pv.run(FakeProvider(), pv.GenRequest("txt2img", "x", (8, 8)), cache)
    stored = (tmp_path / res.request_hash[:2] / res.request_hash / "response.json").read_text()
    assert "secret" not in stored and json.loads(stored)["raw"] == {"id": "r1"}


def test_request_hash_depends_on_image_bytes_not_path(tmp_path: Path) -> None:
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    a.write_bytes(_png((1, 2, 3)))
    b.write_bytes(_png((1, 2, 3)))
    ra = pv.GenRequest("img2img", "x", (8, 8), init_image=a)
    rb = pv.GenRequest("img2img", "x", (8, 8), init_image=b)
    assert pv.request_hash("p", ra) == pv.request_hash("p", rb)
    b.write_bytes(_png((9, 9, 9)))
    assert pv.request_hash("p", ra) != pv.request_hash("p", rb)
    assert pv.request_hash("p", ra) != pv.request_hash("q", ra)


def test_unsupported_mode_is_refused_before_call(tmp_path: Path) -> None:
    prov = FakeProvider()
    img = tmp_path / "i.png"
    img.write_bytes(_png((0, 0, 0)))
    req = pv.GenRequest("inpaint", "x", (8, 8), init_image=img, mask=img)
    with pytest.raises(pv.ProviderError) as e:
        pv.run(prov, req)
    assert e.value.code == "capability_missing" and prov.calls == 0


def test_request_validation_rejects_bad_n_and_missing_inputs() -> None:
    with pytest.raises(pv.ProviderError, match="n must be"):
        pv.GenRequest("txt2img", "x", (8, 8), n=5)
    with pytest.raises(pv.ProviderError, match="init image"):
        pv.GenRequest("img2img", "x", (8, 8))


def test_guard_runs_only_on_cache_miss(tmp_path: Path) -> None:
    seen: list[float] = []
    prov, cache = FakeProvider(), pv.Cache(tmp_path)
    req = pv.GenRequest("txt2img", "x", (8, 8))
    pv.run(prov, req, cache, guard=lambda p, r, usd: seen.append(usd))
    pv.run(prov, req, cache, guard=lambda p, r, usd: seen.append(usd))
    assert seen == [pytest.approx(0.04)]


def test_send_retries_twice_on_429_then_raises() -> None:
    calls: list[int] = []

    def transport(req: HttpRequest, timeout: float) -> HttpResponse:
        calls.append(1)
        return HttpResponse(429, b"slow down")

    with pytest.raises(pv.ProviderError) as e:
        send(transport, HttpRequest("GET", "http://x"), sleep=lambda s: None)
    assert len(calls) == 3 and e.value.code == "provider_error"


def test_send_recovers_after_one_503() -> None:
    answers = iter([HttpResponse(503, b""), HttpResponse(200, b"ok")])
    resp = send(lambda r, t: next(answers), HttpRequest("GET", "http://x"), sleep=lambda s: None)
    assert resp.body == b"ok"


def test_registry_unknown_provider_lists_known() -> None:
    pv.register("fake-test", FakeProvider)
    assert isinstance(pv.get("fake-test"), FakeProvider)
    with pytest.raises(pv.ProviderError, match="fake-test"):
        pv.get("nope")
