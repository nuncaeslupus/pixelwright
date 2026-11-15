"""`pw view`: a local HTTP viewer over one workspace (stdlib only).

The JSON API calls the same command handlers as the CLI, so the viewer has no business
logic of its own. Every request must come from this machine with a local `Host`; every
write must carry the per-run token the page embeds (`X-PW-Token`).
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import re
import secrets
import tempfile
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import numpy as np

from pixelwright.cli.registry import REGISTRY, Outcome, PwError
from pixelwright.core.image import RGBImage
from pixelwright.core.render import grayscale, value_map
from pixelwright.io.aseprite import flatten_frames, read_aseprite
from pixelwright.io.png import encode_png, read_png
from pixelwright.workspace import Workspace

TOKEN_HEADER = "X-PW-Token"
STATIC = resources.files("pixelwright.viewer") / "static"
IMAGE_VIEWS = ("color", "gray", "values", "silhouette")
MAX_BODY = 8 * 1024 * 1024
STATUS = {"not_found": 404, "forbidden": 403, "exists": 409, "internal": 500}
TYPES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".png": "image/png"}
TYPES |= {".woff2": "font/woff2", ".svg": "image/svg+xml", ".txt": "text/plain"}


class Reply:
    """A response body: JSON, or raw bytes with a content type."""

    def __init__(self, body: Any, content_type: str = "application/json", status: int = 200):
        self.body, self.content_type, self.status = body, content_type, status


class Viewer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, root: Path, port: int = 0, token: str | None = None) -> None:
        super().__init__(("127.0.0.1", port), Handler)
        self.root = root
        self.token = token or secrets.token_urlsafe(24)

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def start(self) -> Viewer:
        threading.Thread(target=self.serve_forever, daemon=True).start()
        return self


# -- endpoints ------------------------------------------------------------------
Query = dict[str, str]
Body = dict[str, Any]
Route = Callable[["Viewer", Query, Body, dict[str, str]], Reply]
ROUTES: list[tuple[str, re.Pattern[str], Route]] = []
ID = r"(?P<asset>[a-z0-9][a-z0-9-]*)"
VER = r"(?P<version>v\d{4})"


def route(method: str, pattern: str) -> Callable[[Route], Route]:
    def register(fn: Route) -> Route:
        ROUTES.append((method, re.compile(pattern), fn))
        return fn

    return register


def cli(viewer: Viewer, name: str, **args: Any) -> Outcome:
    from pixelwright.cli import run

    return run(REGISTRY[name], args, viewer.root)


def _status_line(row: dict[str, Any]) -> str:
    if row["newest"] is None:
        return "no versions yet"
    parts = [row["versions"][-1]["stage"]]
    if row["waiting_for_decision"]:
        parts.append("waiting for your decision")
    if row["open_issues"]:
        parts.append(f"{row['open_issues']} open issue" + ("s" * (row["open_issues"] > 1)))
    return " · ".join(parts)


@route("GET", r"/api/assets")
def assets(v: Viewer, q: Query, b: Body, p: dict[str, str]) -> Reply:
    rows = cli(v, "status").data["assets"]
    cards = [
        {
            "id": r["asset"],
            "kind": r["kind"],
            "newest": r["newest"],
            "stage": r["versions"][-1]["stage"] if r["versions"] else None,
            "status": _status_line(r),
            "open_issues": r["open_issues"],
            "thumbnail": f"/api/assets/{r['asset']}/{r['newest']}/image.png"
            if r["newest"]
            else None,
        }
        for r in rows
    ]
    return Reply({"assets": cards})


@route("GET", rf"/api/assets/{ID}")
def asset_detail(v: Viewer, q: Query, b: Body, p: dict[str, str]) -> Reply:
    asset = Workspace.open(v.root).asset(p["asset"])
    versions = []
    for name in asset.versions():
        meta = asset.meta(name)
        stage = asset.stage(name)
        versions.append(
            {"version": name, "stage": stage, "parent": meta["parent"], "step": meta["step"]}
        )
    events = cli(v, "inbox", reader="human").data["items"]
    inbox = sum(e.get("asset") == asset.id for e in events)
    return Reply({"id": asset.id, "spec": asset.spec(), "versions": versions, "inbox": inbox})


def _version_dir(v: Viewer, p: dict[str, str]) -> Path:
    asset = Workspace.open(v.root).asset(p["asset"])
    asset.meta(p["version"])  # must exist
    return asset.versions_dir / p["version"]


@route("GET", rf"/api/assets/{ID}/{VER}/image\.png")
def image(v: Viewer, q: Query, b: Body, p: dict[str, str]) -> Reply:
    folder = _version_dir(v, p)
    view = q.get("view", "color")
    if view not in IMAGE_VIEWS:
        raise PwError("invalid", f"view must be one of {IMAGE_VIEWS}")
    if "frame" in q:
        frames = _frames(folder)
        index = int(q["frame"])
        if not 0 <= index < len(frames):
            raise PwError("not_found", f"no frame {index}")
        rgba = frames[index][0]
    elif view == "color":
        return Reply((folder / "image.png").read_bytes(), "image/png")
    else:
        rgba = read_png(folder / "image.png").to_rgba()
    if view == "gray":
        rgba = grayscale(rgba)
    elif view == "values":
        rgba = value_map(rgba)
    elif view == "silhouette":
        rgba = np.where(rgba[..., 3:] > 0, np.array([0, 0, 0, 255], np.uint8), 0).astype(np.uint8)
    return Reply(encode_png(RGBImage(np.ascontiguousarray(rgba))), "image/png")


@route("GET", rf"/api/assets/{ID}/{VER}/report")
def report(v: Viewer, q: Query, b: Body, p: dict[str, str]) -> Reply:
    path = _version_dir(v, p) / "report.json"
    if not path.is_file():
        raise PwError("not_found", f"{p['asset']} {p['version']} has no report; run `pw check`")
    return Reply(json.loads(path.read_text(encoding="utf-8")))


def _frames(folder: Path) -> list[tuple[Any, int]]:
    ase = folder / "image.aseprite"
    if ase.is_file():
        return flatten_frames(read_aseprite(ase))
    return [(read_png(folder / "image.png").to_rgba(), 100)]


@route("GET", rf"/api/assets/{ID}/{VER}/frames")
def frames(v: Viewer, q: Query, b: Body, p: dict[str, str]) -> Reply:
    folder = _version_dir(v, p)
    ase = folder / "image.aseprite"
    tags = []
    if ase.is_file():
        tags = [
            {"name": t.name, "start": t.start, "end": t.end, "direction": t.direction}
            for t in read_aseprite(ase).tags()
        ]
    durations = [d for _, d in _frames(folder)]
    base = f"/api/assets/{p['asset']}/{p['version']}/image.png?frame="
    return Reply(
        {
            "frames": len(durations),
            "durations": durations,
            "tags": tags,
            "urls": [f"{base}{i}" for i in range(len(durations))],
            "layered": ase.is_file(),
        }
    )


@route("GET", rf"/api/assets/{ID}/diff")
def diff(v: Viewer, q: Query, b: Body, p: dict[str, str]) -> Reply:
    if not q.get("a") or not q.get("b"):
        raise PwError("invalid", "diff needs ?a=<version>&b=<version>")
    out = cli(v, "diff", asset=p["asset"], version_a=q["a"], version_b=q["b"])
    return Reply({**out.data, "image": "/" + out.outputs[0]})


@route("GET", rf"/api/assets/{ID}/issues")
def issues(v: Viewer, q: Query, b: Body, p: dict[str, str]) -> Reply:
    listed = cli(v, "issue", asset=p["asset"], action="list").data["issues"]
    if q.get("version"):
        listed = [i for i in listed if i.get("version") in (None, q["version"])]
    critique = None
    try:
        critique = cli(v, "critique", asset=p["asset"], action="show", version=q.get("version"))
    except PwError as err:
        if err.code != "not_found":
            raise
    return Reply({"issues": listed, "critique": critique.data if critique else None})


@route("GET", rf"/api/assets/{ID}/history")
def history(v: Viewer, q: Query, b: Body, p: dict[str, str]) -> Reply:
    limit = int(q.get("limit", 200))
    return Reply(cli(v, "history", asset=p["asset"], since=q.get("since"), limit=limit).data)


@route("GET", r"/api/inbox")
def inbox(v: Viewer, q: Query, b: Body, p: dict[str, str]) -> Reply:
    return Reply(cli(v, "inbox", since=q.get("since"), reader="human").data)


@route("POST", rf"/api/assets/{ID}/issues")
def add_issue(v: Viewer, q: Query, b: Body, p: dict[str, str]) -> Reply:
    box = b.get("box")
    args: dict[str, Any] = {
        "asset": p["asset"],
        "action": "add",
        "id": b.get("id"),
        "box": ",".join(str(int(n)) for n in box) if isinstance(box, list) else box,
        "version": b.get("version"),
        "rule": b.get("rule", ""),
        "note": b.get("note", ""),
        "author": b.get("author", "human"),
    }
    if not b.get("png"):
        return Reply(cli(v, "issue", **args).data, status=201)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "mask.png"
        path.write_bytes(base64.b64decode(str(b["png"]).split(",")[-1], validate=True))
        return Reply(cli(v, "issue", **args, file=str(path)).data, status=201)


@route("POST", rf"/api/assets/{ID}/issues/(?P<issue>[a-z0-9-]+)/resolve")
def resolve_issue(v: Viewer, q: Query, b: Body, p: dict[str, str]) -> Reply:
    args = {"asset": p["asset"], "action": "resolve", "id": p["issue"]}
    out = cli(v, "issue", **args, version=b.get("version"), author=b.get("author", "human"))
    return Reply(out.data)


@route("POST", rf"/api/assets/{ID}/{VER}/decision")
def decision(v: Viewer, q: Query, b: Body, p: dict[str, str]) -> Reply:
    choice, note = b.get("decision"), str(b.get("note", "")).strip()
    if choice not in ("approve", "reject"):
        raise PwError("invalid", "decision must be approve or reject")
    if choice == "reject" and not note:
        raise PwError("invalid", "a rejection needs a note: what should change?")
    out = cli(v, choice, asset=p["asset"], version=p["version"], note=note, author="human")
    return Reply({"decision": choice, "version": out.version, "stage": out.stage})


@route("POST", rf"/api/assets/{ID}/revert")
def revert(v: Viewer, q: Query, b: Body, p: dict[str, str]) -> Reply:
    ws = Workspace.open(v.root)
    asset = ws.asset(p["asset"])
    undone = asset.revert_decision(author=b.get("author", "human"))
    ws.refresh_gitignore()
    version = undone["version"]
    return Reply(
        {"reverted": undone["decision"], "version": version, "stage": asset.stage(version)}
    )


# -- HTTP plumbing -----------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server: Viewer
    server_version = "pixelwright"

    def log_message(self, format: str, *args: Any) -> None:  # quiet
        pass

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def _local(self) -> bool:
        hosts = {f"127.0.0.1:{self.server.port}", f"localhost:{self.server.port}"}
        return self.client_address[0] in ("127.0.0.1", "::1") and self.headers.get("Host") in hosts

    def _dispatch(self, method: str) -> None:
        try:
            if not self._local():
                raise PwError("forbidden", "the viewer only answers local requests")
            url = urlsplit(self.path)
            if method == "POST":
                given = self.headers.get(TOKEN_HEADER, "")
                if not hmac.compare_digest(given.encode(), self.server.token.encode()):
                    raise PwError("forbidden", f"writes need the {TOKEN_HEADER} header")
            query = {k: vals[-1] for k, vals in parse_qs(url.query).items()}
            for verb, pattern, fn in ROUTES:
                match = pattern.fullmatch(url.path)
                if verb == method and match:
                    self._send(fn(self.server, query, self._body(method), match.groupdict()))
                    return
            if method == "GET" and not url.path.startswith("/api/"):
                self._send(self._static(url.path))
                return
            raise PwError("not_found", f"no endpoint {method} {url.path}")
        except Exception as exc:  # every failure answers with the CLI error shape
            self._send(_error_reply(exc))

    def _body(self, method: str) -> Body:
        if method != "POST":
            return {}
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise PwError("invalid", "request body too large")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError as exc:
            raise PwError("invalid", f"body is not JSON: {exc}") from exc
        if not isinstance(body, dict):
            raise PwError("invalid", "body must be a JSON object")
        return body

    def _static(self, path: str) -> Reply:
        if path in ("/", "/index.html"):
            page = (STATIC / "index.html").read_text(encoding="utf-8")
            return Reply(page.replace("{{TOKEN}}", self.server.token).encode(), "text/html")
        parts = [s for s in path.split("/") if s]
        if not parts or any(s in ("..", ".") or s.startswith(".") for s in parts):
            raise PwError("not_found", f"no file {path}")
        if parts[0] == "cache":  # renders the API points at (diff overlays)
            file = Workspace.open(self.server.root).path("cache").joinpath(*parts[1:])
            if not file.is_file():
                raise PwError("not_found", f"no file {path}")
            return Reply(file.read_bytes(), TYPES.get(file.suffix, "application/octet-stream"))
        if parts[0] != "static":
            raise PwError("not_found", f"no file {path}")
        res = STATIC.joinpath(*parts[1:])
        if not res.is_file():
            raise PwError("not_found", f"no file {path}")
        return Reply(
            res.read_bytes(), TYPES.get(Path(parts[-1]).suffix, "application/octet-stream")
        )

    def _send(self, reply: Reply) -> None:
        body = reply.body
        if reply.content_type == "application/json":
            body = json.dumps(body, default=_jsonable).encode()
        self.send_response(reply.status)
        self.send_header("Content-Type", reply.content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def _error_reply(exc: Exception) -> Reply:
    from pixelwright.cli import as_error

    try:
        err = as_error(exc)
    except Exception:
        err = PwError("internal", f"{type(exc).__name__}: {exc}")
    if isinstance(exc, (KeyError, IndexError, TypeError, binascii.Error)):
        err = PwError("invalid", str(exc))
    body = {
        "ok": False,
        "error": {"code": err.code, "message": err.message, "details": err.details},
    }
    return Reply(body, status=STATUS.get(err.code, 400))


def _jsonable(value: object) -> object:
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    if isinstance(value, (tuple, set)):
        return list(value)
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")
