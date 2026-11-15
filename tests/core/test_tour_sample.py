"""The tour's sample art and the replay provider."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from pixelwright.core import providers as pv
from pixelwright.core.snap import snap
from pixelwright.fixtures import tour
from pixelwright.io.png import encode_png


def _digest(img: object) -> str:
    return hashlib.sha256(encode_png(img)).hexdigest()  # type: ignore[arg-type]


def test_tour_sample_is_deterministic() -> None:
    assert _digest(tour.sketch()) == _digest(tour.sketch())
    assert _digest(tour.painted()) == _digest(tour.painted())
    assert tour.painted().width == tour.WIDTH * tour.SCALE


def test_painted_sample_snaps_back_to_native_grid() -> None:
    result = snap(tour.painted())
    assert result.scale == tour.SCALE


def test_replay_prefers_recorded_answer_then_pool(tmp_path: Path) -> None:
    (tmp_path / "a.png").write_bytes(encode_png(tour.sketch()))
    (tmp_path / "b.png").write_bytes(encode_png(tour.painted()))
    prov = pv.get("replay", folder=tmp_path)
    req = pv.GenRequest("txt2img", "house", (160, 90), n=2)
    pooled = pv.run(prov, req)
    assert sorted(pooled.raw["replay"]) == ["a.png", "b.png"] and pooled.cost.usd == 0.0
    key = pv.request_hash("replay", req)
    rec = tmp_path / key[:2] / key
    rec.mkdir(parents=True)
    (rec / "out_0.png").write_bytes(b"recorded")
    assert pv.run(prov, req).images == [b"recorded"]


def test_replay_without_images_says_where_it_looked(tmp_path: Path) -> None:
    prov = pv.get("replay", folder=tmp_path)
    try:
        pv.run(prov, pv.GenRequest("txt2img", "x", (8, 8)))
    except pv.ProviderError as e:
        assert e.code == "provider_unavailable" and str(tmp_path) in e.message
    else:
        raise AssertionError("expected ProviderError")


def test_sketch_is_mostly_paper() -> None:
    rgb = tour.sketch().rgba[..., :3].astype(int)
    assert (rgb.mean(axis=2) > 200).mean() > 0.8
    assert np.unique(tour.scene().indices).size == len(tour.PALETTE_HEX)
