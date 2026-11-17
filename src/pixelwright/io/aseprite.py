"""Reader and writer for the documented `.aseprite` / `.ase` format.

Covers the header, frames (durations), layers, cels (raw, linked, compressed images;
compressed tilemaps kept as bytes), tags, palette (new chunk, old chunks read), slices
and user data. Every chunk keeps its place in its frame and chunks this module does not
model are kept as raw bytes, so a read-write round trip loses nothing. Cel images are
always written zlib-compressed; equality is semantic (decoded pixels), not byte-exact.
Format reference: aseprite/docs/ase-file-specs.md.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import numpy.typing as npt

from pixelwright.files import write_bytes_atomic

HEADER_MAGIC = 0xA5E0
FRAME_MAGIC = 0xF1FA
HEADER_SIZE = 128
FRAME_HEADER_SIZE = 16

OLD_PALETTE_4 = 0x0004
OLD_PALETTE_11 = 0x0011
LAYER = 0x2004
CEL = 0x2005
TAGS = 0x2018
PALETTE = 0x2019
USER_DATA = 0x2020
SLICE = 0x2022

CEL_RAW, CEL_LINKED, CEL_COMPRESSED, CEL_TILEMAP = 0, 1, 2, 3
CHANNELS = {32: 4, 16: 2, 8: 1}


class AsepriteError(ValueError):
    """The file is not a valid `.aseprite` file or uses an unsupported variant."""


# -- byte helpers ------------------------------------------------------------------------
class _Reader:
    def __init__(self, data: bytes, pos: int = 0) -> None:
        self.data, self.pos = data, pos

    def take(self, fmt: str) -> tuple[int, ...]:
        size = struct.calcsize(fmt)
        if self.pos + size > len(self.data):
            raise AsepriteError("unexpected end of data")
        values = struct.unpack_from(fmt, self.data, self.pos)
        self.pos += size
        return values

    def one(self, fmt: str) -> int:
        return self.take(fmt)[0]

    def read(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise AsepriteError("unexpected end of data")
        out = self.data[self.pos : self.pos + n]
        self.pos += n
        return out

    def string(self) -> str:
        return self.read(self.one("<H")).decode("utf-8")

    def rest(self) -> bytes:
        return self.read(len(self.data) - self.pos)


def _string(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack("<H", len(raw)) + raw


# -- model -------------------------------------------------------------------------------
@dataclass
class PaletteEntry:
    r: int
    g: int
    b: int
    a: int = 255
    name: str = ""


@dataclass
class Layer:
    name: str
    flags: int = 3  # visible | editable
    type: int = 0  # 0 normal, 1 group, 2 tilemap
    child_level: int = 0
    blend_mode: int = 0
    opacity: int = 255
    tileset_index: int = 0
    tail: bytes = b""  # bytes after the documented fields (e.g. a layer UUID)


@dataclass
class Cel:
    layer: int
    x: int = 0
    y: int = 0
    opacity: int = 255
    kind: int = CEL_COMPRESSED
    z_index: int = 0
    pixels: npt.NDArray[np.uint8] | None = None  # H x W x channels for image cels
    link: int = 0  # frame index for linked cels
    tilemap: bytes = b""  # raw body of a compressed tilemap cel

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Cel):
            return NotImplemented
        images = (CEL_RAW, CEL_COMPRESSED)  # same content, different storage
        same_kind = self.kind == other.kind or (self.kind in images and other.kind in images)
        pixels_equal = (self.pixels is None and other.pixels is None) or (
            self.pixels is not None
            and other.pixels is not None
            and np.array_equal(self.pixels, other.pixels)
        )
        return (
            same_kind
            and pixels_equal
            and (self.layer, self.x, self.y, self.opacity, self.z_index, self.link)
            == (other.layer, other.x, other.y, other.opacity, other.z_index, other.link)
            and self.tilemap == other.tilemap
        )


@dataclass
class Tag:
    name: str
    start: int
    end: int
    direction: int = 0  # 0 forward, 1 reverse, 2 ping-pong, 3 ping-pong reverse
    repeat: int = 0
    color: tuple[int, int, int] = (0, 0, 0)


@dataclass
class SliceKey:
    frame: int
    x: int
    y: int
    width: int
    height: int
    center: tuple[int, int, int, int] | None = None  # 9-patch
    pivot: tuple[int, int] | None = None


@dataclass
class Slice:
    name: str
    keys: list[SliceKey] = field(default_factory=list)


@dataclass
class UserData:
    text: str | None = None
    color: tuple[int, int, int, int] | None = None
    properties: bytes = b""  # raw properties maps, kept as is


@dataclass
class RawChunk:
    type: int
    data: bytes


Chunk = (
    PaletteEntry | Layer | Cel | Tag | Slice | UserData | RawChunk | list[PaletteEntry] | list[Tag]
)


@dataclass
class Frame:
    duration: int = 100
    chunks: list[Chunk] = field(default_factory=list)


@dataclass
class AseDocument:
    width: int
    height: int
    depth: int = 32  # 32 RGBA, 16 grayscale, 8 indexed
    flags: int = 1
    transparent_index: int = 0
    pixel_ratio: tuple[int, int] = (1, 1)
    grid: tuple[int, int, int, int] = (0, 0, 16, 16)
    frames: list[Frame] = field(default_factory=list)

    # Convenience views over the chunks.
    def layers(self) -> list[Layer]:
        return [c for f in self.frames for c in f.chunks if isinstance(c, Layer)]

    def palette(self) -> list[PaletteEntry]:
        for f in self.frames:
            for c in f.chunks:
                if isinstance(c, list) and (not c or isinstance(c[0], PaletteEntry)):
                    return [e for e in c if isinstance(e, PaletteEntry)]
        return []

    def tags(self) -> list[Tag]:
        out: list[Tag] = []
        for f in self.frames:
            for c in f.chunks:
                if isinstance(c, list) and c and isinstance(c[0], Tag):
                    out += [t for t in c if isinstance(t, Tag)]
        return out

    def slices(self) -> list[Slice]:
        return [c for f in self.frames for c in f.chunks if isinstance(c, Slice)]

    def cels(self, frame: int) -> list[Cel]:
        return [c for c in self.frames[frame].chunks if isinstance(c, Cel)]


# -- reading -----------------------------------------------------------------------------
def _read_cel(r: _Reader, depth: int, end: int) -> Cel:
    layer, x, y, opacity, kind, z = r.take("<HhhBHh")
    r.read(5)
    cel = Cel(layer, x, y, opacity, kind, z)
    ch = CHANNELS[depth]
    if kind == CEL_RAW:
        w, h = r.take("<HH")
        cel.pixels = np.frombuffer(r.read(w * h * ch), np.uint8).reshape(h, w, ch).copy()
    elif kind == CEL_COMPRESSED:
        w, h = r.take("<HH")
        try:
            raw = zlib.decompress(r.read(end - r.pos))
        except zlib.error as exc:
            raise AsepriteError(f"bad compressed cel: {exc}") from exc
        if len(raw) != w * h * ch:
            raise AsepriteError("compressed cel has the wrong size")
        cel.pixels = np.frombuffer(raw, np.uint8).reshape(h, w, ch).copy()
    elif kind == CEL_LINKED:
        cel.link = r.one("<H")
    else:
        cel.tilemap = r.read(end - r.pos)
    return cel


def _read_user_data(r: _Reader) -> UserData:
    flags = r.one("<I")
    ud = UserData()
    if flags & 1:
        ud.text = r.string()
    if flags & 2:
        rr, g, b, a = r.take("<BBBB")
        ud.color = (rr, g, b, a)
    if flags & 4:
        ud.properties = r.rest()
    return ud


def _read_chunk(ctype: int, body: bytes, depth: int) -> Chunk:
    r = _Reader(body)
    if ctype == LAYER:
        flags, ltype, level, _w, _h, blend, opacity = r.take("<HHHHHHB")
        r.read(3)
        layer = Layer(r.string(), flags, ltype, level, blend, opacity)
        if ltype == 2:
            layer.tileset_index = r.one("<I")
        layer.tail = r.rest()
        return layer
    if ctype == CEL:
        return _read_cel(r, depth, len(body))
    if ctype == PALETTE:
        _size, first, last = r.take("<III")
        r.read(8)
        entries = []
        for _ in range(first, last + 1):
            flags, rr, g, b, a = r.take("<HBBBB")
            entries.append(PaletteEntry(rr, g, b, a, r.string() if flags & 1 else ""))
        return entries
    if ctype == TAGS:
        count = r.one("<H")
        r.read(8)
        tags = []
        for _ in range(count):
            start, end, direction, repeat = r.take("<HHBH")
            r.read(6)
            rgb = r.take("<BBB")
            r.read(1)
            tags.append(Tag(r.string(), start, end, direction, repeat, (rgb[0], rgb[1], rgb[2])))
        return tags
    if ctype == SLICE:
        count, flags, _reserved = r.take("<III")
        sl = Slice(r.string())
        for _ in range(count):
            frame, x, y, w, h = r.take("<IiiII")
            key = SliceKey(frame, x, y, w, h)
            if flags & 1:
                cx, cy, cw, chh = r.take("<iiII")
                key.center = (cx, cy, cw, chh)
            if flags & 2:
                px, py = r.take("<ii")
                key.pivot = (px, py)
            sl.keys.append(key)
        return sl
    if ctype == USER_DATA:
        return _read_user_data(r)
    return RawChunk(ctype, body)


def parse(data: bytes) -> AseDocument:
    r = _Reader(data)
    (_size, magic, nframes, width, height, depth, flags) = r.take("<IHHHHHI")
    if magic != HEADER_MAGIC:
        raise AsepriteError("not an .aseprite file (bad header magic)")
    if depth not in CHANNELS:
        raise AsepriteError(f"unsupported color depth {depth}")
    r.take("<HII")  # speed (deprecated), two reserved DWORDs
    transparent = r.one("<B")
    r.read(3)
    r.one("<H")  # number of colors (informative)
    pw, ph = r.take("<BB")
    gx, gy, gw, gh = r.take("<hhHH")
    doc = AseDocument(
        width, height, depth, flags, transparent, (pw or 1, ph or 1), (gx, gy, gw, gh)
    )
    r.pos = HEADER_SIZE
    for _ in range(nframes):
        start = r.pos
        fsize, fmagic, old_count, duration = r.take("<IHHH")
        if fmagic != FRAME_MAGIC:
            raise AsepriteError("bad frame magic")
        r.read(2)
        new_count = r.one("<I")
        count = new_count or old_count
        frame = Frame(duration)
        for _ in range(count):
            csize, ctype = r.take("<IH")
            if csize < 6:
                raise AsepriteError("bad chunk size")
            body = r.read(csize - 6)
            if ctype in (OLD_PALETTE_4, OLD_PALETTE_11):
                frame.chunks.append(RawChunk(ctype, body))
            else:
                frame.chunks.append(_read_chunk(ctype, body, depth))
        r.pos = start + fsize
        doc.frames.append(frame)
    return doc


def read_aseprite(path: Path) -> AseDocument:
    return parse(path.read_bytes())


# -- writing -----------------------------------------------------------------------------
def _write_chunk(chunk: Chunk, depth: int) -> tuple[int, bytes]:
    if isinstance(chunk, RawChunk):
        return chunk.type, chunk.data
    if isinstance(chunk, Layer):
        body = struct.pack(
            "<HHHHHHB3x",
            chunk.flags,
            chunk.type,
            chunk.child_level,
            0,
            0,
            chunk.blend_mode,
            chunk.opacity,
        ) + _string(chunk.name)
        if chunk.type == 2:
            body += struct.pack("<I", chunk.tileset_index)
        return LAYER, body + chunk.tail
    if isinstance(chunk, Cel):
        kind = CEL_COMPRESSED if chunk.kind == CEL_RAW else chunk.kind
        head = struct.pack(
            "<HhhBHh5x", chunk.layer, chunk.x, chunk.y, chunk.opacity, kind, chunk.z_index
        )
        if kind == CEL_COMPRESSED:
            if chunk.pixels is None or chunk.pixels.shape[2] != CHANNELS[depth]:
                raise AsepriteError("image cel needs pixels matching the color depth")
            h, w = chunk.pixels.shape[:2]
            payload = zlib.compress(np.ascontiguousarray(chunk.pixels, np.uint8).tobytes())
            return CEL, head + struct.pack("<HH", w, h) + payload
        if kind == CEL_LINKED:
            return CEL, head + struct.pack("<H", chunk.link)
        return CEL, head + chunk.tilemap
    if isinstance(chunk, UserData):
        flags = (1 if chunk.text is not None else 0) | (2 if chunk.color else 0)
        flags |= 4 if chunk.properties else 0
        body = struct.pack("<I", flags)
        if chunk.text is not None:
            body += _string(chunk.text)
        if chunk.color:
            body += struct.pack("<BBBB", *chunk.color)
        return USER_DATA, body + chunk.properties
    if isinstance(chunk, Slice):
        flags = (1 if any(k.center for k in chunk.keys) else 0) | (
            2 if any(k.pivot for k in chunk.keys) else 0
        )
        body = struct.pack("<III", len(chunk.keys), flags, 0) + _string(chunk.name)
        for k in chunk.keys:
            body += struct.pack("<IiiII", k.frame, k.x, k.y, k.width, k.height)
            if flags & 1:
                body += struct.pack("<iiII", *(k.center or (0, 0, 0, 0)))
            if flags & 2:
                body += struct.pack("<ii", *(k.pivot or (0, 0)))
        return SLICE, body
    if isinstance(chunk, list) and chunk and isinstance(chunk[0], Tag):
        body = struct.pack("<H8x", len(chunk))
        for t in chunk:
            assert isinstance(t, Tag)
            body += struct.pack("<HHBH6xBBBx", t.start, t.end, t.direction, t.repeat, *t.color)
            body += _string(t.name)
        return TAGS, body
    if isinstance(chunk, list):
        entries = [e for e in chunk if isinstance(e, PaletteEntry)]
        body = struct.pack("<III8x", len(entries), 0, max(len(entries) - 1, 0))
        for e in entries:
            body += struct.pack("<HBBBB", 1 if e.name else 0, e.r, e.g, e.b, e.a)
            if e.name:
                body += _string(e.name)
        return PALETTE, body
    raise AsepriteError(f"cannot write chunk {chunk!r}")


def serialize(doc: AseDocument) -> bytes:
    if doc.depth not in CHANNELS:
        raise AsepriteError(f"unsupported color depth {doc.depth}")
    frames = b""
    for frame in doc.frames:
        body = b""
        for chunk in frame.chunks:
            ctype, data = _write_chunk(chunk, doc.depth)
            body += struct.pack("<IH", len(data) + 6, ctype) + data
        count = len(frame.chunks)
        head = struct.pack(
            "<IHHH2xI",
            FRAME_HEADER_SIZE + len(body),
            FRAME_MAGIC,
            min(count, 0xFFFF),
            frame.duration,
            count,
        )
        frames += head + body
    ncolors = len(doc.palette()) or (256 if doc.depth == 8 else 0)
    header = struct.pack(
        "<IHHHHHIHIIB3xHBBhhHH84x",
        HEADER_SIZE + len(frames),
        HEADER_MAGIC,
        len(doc.frames),
        doc.width,
        doc.height,
        doc.depth,
        doc.flags,
        100,
        0,
        0,
        doc.transparent_index,
        ncolors if ncolors < 256 else 0,
        *doc.pixel_ratio,
        *doc.grid,
    )
    assert len(header) == HEADER_SIZE
    return header + frames


def write_aseprite(path: Path, doc: AseDocument) -> None:
    write_bytes_atomic(path, serialize(doc))


# -- flattening --------------------------------------------------------------------------
def flatten_frames(doc: AseDocument) -> list[tuple[npt.NDArray[np.uint8], int]]:
    """Each frame as an H x W x 4 RGBA image (visible normal layers, alpha over) + duration."""
    layers = doc.layers()
    palette = doc.palette()
    lut = np.zeros((256, 4), np.uint8)
    for i, e in enumerate(palette[:256]):
        lut[i] = (e.r, e.g, e.b, e.a)
    if doc.depth == 8 and doc.transparent_index < 256:
        lut[doc.transparent_index, 3] = 0
    out = []
    for f, frame in enumerate(doc.frames):
        canvas = np.zeros((doc.height, doc.width, 4), np.float64)
        cels = sorted(doc.cels(f), key=lambda c: (c.layer + c.z_index, c.z_index))
        for cel in cels:
            if cel.kind == CEL_LINKED:
                linked = [c for c in doc.cels(cel.link) if c.layer == cel.layer]
                if not linked:
                    continue
                cel = linked[0]
            if cel.pixels is None or cel.layer >= len(layers):
                continue
            layer = layers[cel.layer]
            if not layer.flags & 1 or layer.type != 0:
                continue
            rgba = _cel_rgba(cel.pixels, doc.depth, lut)
            h, w = rgba.shape[:2]
            y0, x0 = max(cel.y, 0), max(cel.x, 0)
            y1, x1 = min(cel.y + h, doc.height), min(cel.x + w, doc.width)
            if y1 <= y0 or x1 <= x0:
                continue
            src = rgba[y0 - cel.y : y1 - cel.y, x0 - cel.x : x1 - cel.x].astype(np.float64)
            alpha = src[..., 3:] / 255 * (cel.opacity / 255) * (layer.opacity / 255)
            dst = canvas[y0:y1, x0:x1]
            out_a = alpha + dst[..., 3:] / 255 * (1 - alpha)
            safe = np.where(out_a > 0, out_a, 1)
            rgb = (src[..., :3] * alpha + dst[..., :3] * (dst[..., 3:] / 255) * (1 - alpha)) / safe
            dst[..., :3], dst[..., 3:] = rgb, out_a * 255
        out.append((np.rint(canvas).astype(np.uint8), frame.duration))
    return out


def _cel_rgba(
    pixels: npt.NDArray[np.uint8], depth: int, lut: npt.NDArray[np.uint8]
) -> npt.NDArray[np.uint8]:
    if depth == 32:
        return pixels
    if depth == 16:
        v, a = pixels[..., 0], pixels[..., 1]
        return np.dstack([v, v, v, a]).astype(np.uint8)
    return lut[pixels[..., 0]]
