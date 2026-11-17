import base64
import http.client
import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image as PILImage

from pixelwright.cli import main
from pixelwright.core.image import RGBImage
from pixelwright.core.palette import Color, Palette
from pixelwright.io.aseprite import AseDocument, Cel, Frame, Layer, Tag, write_aseprite
from pixelwright.io.palette_io import write_palette
from pixelwright.io.png import encode_png, write_png
from pixelwright.viewer.server import ROUTES, TOKEN_HEADER, Viewer
from pixelwright.workspace import Workspace

COLORS = [(20, 20, 30), (200, 60, 40), (240, 220, 160), (40, 120, 200)]


@pytest.fixture
def viewer(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Iterator[Viewer]:
    rng = np.random.default_rng(0)
    native = np.array(COLORS, np.uint8)[rng.integers(0, 4, (12, 16))]
    write_png(tmp_path / "src.png", RGBImage(np.dstack([native, np.full((12, 16), 255, np.uint8)])))
    write_palette(tmp_path / "scene.gpl", Palette([Color(*c) for c in COLORS]))
    root = tmp_path / "ws"
    w = ["--workspace", str(root)]
    for argv in (
        ["init", "--legacy"],
        ["palette", "import", "--file", str(tmp_path / "scene.gpl")],
        ["new", "hero", "--kind", "sprite", "--palette", "palettes/scene.gpl"],
        ["attach", "hero", str(tmp_path / "src.png")],
        ["quantize", "hero"],
        ["check", "hero"],
        ["issue", "hero", "add", "--box", "0,0,4,4", "--rule", "R-PIX-3", "--version", "v0002"],
    ):
        assert main([*argv, *w]) == 0, argv
    capsys.readouterr()
    server = Viewer(root, 0).start()
    yield server
    server.shutdown()
    server.server_close()


def call(
    v: Viewer,
    method: str,
    path: str,
    body: Any = None,
    *,
    token: str | None = "ok",
    host: str | None = None,
) -> tuple[int, Any]:
    conn = http.client.HTTPConnection("127.0.0.1", v.port, timeout=10)
    headers = {"Host": host or f"127.0.0.1:{v.port}", "Content-Type": "application/json"}
    if token is not None:
        headers[TOKEN_HEADER] = v.token if token == "ok" else token
    conn.request(method, path, None if body is None else json.dumps(body), headers)
    res = conn.getresponse()
    raw = res.read()
    ctype = res.getheader("Content-Type", "")
    conn.close()
    return res.status, json.loads(raw) if ctype == "application/json" else raw


def png_size(raw: bytes) -> tuple[int, int]:
    with PILImage.open(io.BytesIO(raw)) as im:
        return im.size


# -- security -----------------------------------------------------------------
def test_write_without_token_is_forbidden(viewer: Viewer) -> None:
    for token in (None, "wrong"):
        status, body = call(
            viewer, "POST", "/api/assets/hero/v0002/decision", {"decision": "approve"}, token=token
        )
        assert status == 403 and body["error"]["code"] == "forbidden"
    assert Workspace.open(viewer.root).asset("hero").decisions() == []


def test_foreign_host_is_forbidden(viewer: Viewer) -> None:
    for host in ("evil.example", f"evil.example:{viewer.port}", "127.0.0.1:1"):
        status, body = call(viewer, "GET", "/api/assets", host=host)
        assert status == 403 and body["error"]["code"] == "forbidden"
    assert call(viewer, "GET", "/api/assets", host=f"localhost:{viewer.port}")[0] == 200


def test_page_embeds_token_and_serves_static(viewer: Viewer) -> None:
    status, page = call(viewer, "GET", "/")
    assert status == 200 and viewer.token.encode() in page
    assert call(viewer, "GET", "/static/fonts/AtkinsonHyperlegibleNext.woff2")[0] == 200
    assert call(viewer, "GET", "/static/../server.py")[0] == 404
    assert call(viewer, "GET", "/api/nothing")[0] == 404


# -- one test per endpoint ------------------------------------------------------
def test_get_assets(viewer: Viewer) -> None:
    status, body = call(viewer, "GET", "/api/assets")
    (card,) = body["assets"]
    assert status == 200 and card["id"] == "hero" and card["newest"] == "v0002"
    assert card["thumbnail"] == "/api/assets/hero/v0002/image.png"
    assert "waiting for your decision" in card["status"] and card["open_issues"] == 1


def test_get_asset(viewer: Viewer) -> None:
    status, body = call(viewer, "GET", "/api/assets/hero")
    assert status == 200 and body["spec"]["kind"] == "sprite"
    assert [(v["version"], v["step"], v["parent"]) for v in body["versions"]] == [
        ("v0001", "attach", None),
        ("v0002", "quantize", "v0001"),
    ]
    assert isinstance(body["inbox"], int)
    assert body["next"]["step"] == "clean" and body["next"]["command"] == "pw clean hero"
    assert call(viewer, "GET", "/api/assets/ghost")[0] == 404


def test_get_image_views(viewer: Viewer) -> None:
    for view in ("color", "gray", "values", "silhouette"):
        status, raw = call(viewer, "GET", f"/api/assets/hero/v0002/image.png?view={view}")
        assert status == 200 and png_size(raw) == (16, 12)
    assert call(viewer, "GET", "/api/assets/hero/v0002/image.png?view=nope")[0] == 400
    assert call(viewer, "GET", "/api/assets/hero/v0009/image.png")[0] == 404


def test_get_report(viewer: Viewer) -> None:
    status, body = call(viewer, "GET", "/api/assets/hero/v0002/report")
    assert status == 200 and body["results"]
    assert call(viewer, "GET", "/api/assets/hero/v0001/report")[0] == 404


def test_get_frames(viewer: Viewer) -> None:
    status, body = call(viewer, "GET", "/api/assets/hero/v0002/frames")
    assert status == 200 and body["frames"] == 1 and not body["layered"]
    px = np.zeros((12, 16, 4), np.uint8)
    px[..., 3] = 255
    frames = [Frame(duration=90, chunks=[Layer("body"), Cel(0, pixels=px)])]
    frames += [Frame(duration=150, chunks=[Cel(0, pixels=px)])]
    frames[0].chunks.append([Tag("walk", 0, 1)])
    write_aseprite(
        viewer.root / "assets/hero/versions/v0002/image.aseprite",
        AseDocument(16, 12, frames=frames),
    )
    body = call(viewer, "GET", "/api/assets/hero/v0002/frames")[1]
    assert body["durations"] == [90, 150] and body["tags"][0]["name"] == "walk"
    status, raw = call(viewer, "GET", body["urls"][1])
    assert status == 200 and png_size(raw) == (16, 12)


def test_get_diff(viewer: Viewer) -> None:
    status, body = call(viewer, "GET", "/api/assets/hero/diff?a=v0001&b=v0002")
    assert status == 200 and "changed" in body and body["checks"] is not None
    assert call(viewer, "GET", body["image"])[0] == 200
    assert call(viewer, "GET", "/api/assets/hero/diff?a=v0001")[0] == 400


def test_get_issues(viewer: Viewer) -> None:
    status, body = call(viewer, "GET", "/api/assets/hero/issues?version=v0002")
    assert status == 200 and body["issues"][0]["rule"] == "R-PIX-3" and body["critique"] is None


def test_get_history(viewer: Viewer) -> None:
    status, body = call(viewer, "GET", "/api/assets/hero/history")
    events = [h["event"] for h in body["history"]]
    assert status == 200 and events[0] == "issue_add"


def test_get_inbox(viewer: Viewer) -> None:
    status, body = call(viewer, "GET", "/api/inbox")
    assert status == 200 and body["count"] >= 1  # Claude's issue_add


def test_post_issue_with_mask_png(viewer: Viewer) -> None:
    mask = np.zeros((12, 16, 4), np.uint8)
    mask[2:5, 3:7] = 255
    png = base64.b64encode(encode_png(RGBImage(mask))).decode()
    status, body = call(
        viewer, "POST", "/api/assets/hero/issues", {"png": png, "note": "hands", "version": "v0002"}
    )
    assert status == 201
    issue = Workspace.open(viewer.root).asset("hero").issue(body["issue"]["id"])
    assert issue["author"] == "human" and issue["region"] == "mask" and issue["note"] == "hands"
    assert call(viewer, "POST", "/api/assets/hero/issues", {"box": [0, 0, 2, 2]})[0] == 201
    assert call(viewer, "POST", "/api/assets/hero/issues", {"png": "%%%"})[0] == 400


def test_post_resolve(viewer: Viewer) -> None:
    status, _ = call(
        viewer, "POST", "/api/assets/hero/issues/r-pix-3-1/resolve", {"version": "v0002"}
    )
    assert status == 200
    issue = Workspace.open(viewer.root).asset("hero").issue("r-pix-3-1")
    assert issue["status"] == "fixed" and issue["fixed_in"] == "v0002"


def test_post_decision(viewer: Viewer) -> None:
    status, body = call(viewer, "POST", "/api/assets/hero/v0002/decision", {"decision": "approve"})
    assert status == 200 and body["stage"] == "approved"
    status, body = call(viewer, "POST", "/api/assets/hero/v0001/decision", {"decision": "reject"})
    assert status == 400 and "note" in body["error"]["message"]
    assert (
        call(
            viewer,
            "POST",
            "/api/assets/hero/v0001/decision",
            {"decision": "reject", "note": "noisy"},
        )[0]
        == 200
    )


def test_post_revert(viewer: Viewer) -> None:
    assert call(viewer, "POST", "/api/assets/hero/revert", {})[0] == 400  # nothing to undo
    call(viewer, "POST", "/api/assets/hero/v0002/decision", {"decision": "approve"})
    status, body = call(viewer, "POST", "/api/assets/hero/revert", {})
    assert status == 200 and body == {"reverted": "approve", "version": "v0002", "stage": "draft"}
    history = Workspace.open(viewer.root).asset("hero").history()
    assert history[-1]["event"] == "decision_revert"


def test_blind_bench_endpoints(viewer: Viewer) -> None:
    from pixelwright.fixtures.bench import bench_workspace

    out = bench_workspace(viewer.root)
    assert call(viewer, "GET", "/api/bench/ghost/pair")[0] == 404
    status, body = call(viewer, "GET", "/api/bench/try/pair")
    pair = body["pair"]
    assert status == 200 and set(pair) == {"a", "b", "left"}  # tokens only, no file names
    status, _ = call(viewer, "GET", f"/api/bench/try/img/{pair['a']}")
    assert status == 200 and call(viewer, "GET", "/api/bench/try/img/000000000000")[0] == 404
    status, body = call(viewer, "POST", "/api/bench/try/vote", {**pair, "winner": "tie"})
    assert status == 200 and body["pair"]["left"] == pair["left"] - 1
    assert (out / "human_pairs.jsonl").read_text().count("tie") == 1


def test_every_endpoint_is_covered() -> None:
    assert len(ROUTES) == 16
