"""`.aseprite` codec tests on fixture files built byte by byte from the format spec."""

import struct
import zlib
from pathlib import Path

import numpy as np
import pytest

from pixelwright.io import aseprite as ase


def _s(text: str) -> bytes:
    raw = text.encode()
    return struct.pack("<H", len(raw)) + raw


def _chunk(ctype: int, body: bytes) -> bytes:
    return struct.pack("<IH", len(body) + 6, ctype) + body


def _frame(duration: int, chunks: list[bytes]) -> bytes:
    body = b"".join(chunks)
    return (
        struct.pack("<IHHH2xI", 16 + len(body), 0xF1FA, len(chunks), duration, len(chunks)) + body
    )


def _file(w: int, h: int, depth: int, frames: list[bytes], transparent: int = 0) -> bytes:
    body = b"".join(frames)
    header = struct.pack(
        "<IHHHHHIHIIB3xHBBhhHH84x",
        128 + len(body),
        0xA5E0,
        len(frames),
        w,
        h,
        depth,
        1,
        100,
        0,
        0,
        transparent,
        4,
        1,
        1,
        0,
        0,
        16,
        16,
    )
    return header + body


def _layer(name: str, ltype: int = 0, level: int = 0, opacity: int = 255) -> bytes:
    return _chunk(0x2004, struct.pack("<HHHHHHB3x", 3, ltype, level, 0, 0, 0, opacity) + _s(name))


def _cel(layer: int, x: int, y: int, kind: int, payload: bytes, opacity: int = 255) -> bytes:
    return _chunk(0x2005, struct.pack("<HhhBHh5x", layer, x, y, opacity, kind, 0) + payload)


def _image(pixels: np.ndarray, compressed: bool) -> bytes:
    h, w = pixels.shape[:2]
    data = pixels.astype(np.uint8).tobytes()
    return struct.pack("<HH", w, h) + (zlib.compress(data) if compressed else data)


RGBA = np.arange(3 * 4 * 4, dtype=np.uint8).reshape(3, 4, 4)
INDEXED = np.array([[0, 1, 2], [3, 2, 1]], dtype=np.uint8)[..., None]
GRAY = np.array([[[10, 255], [200, 128]]], dtype=np.uint8)


def fixture_rgba() -> bytes:
    palette = _chunk(
        0x2019,
        struct.pack("<III8x", 2, 0, 1)
        + struct.pack("<HBBBB", 1, 255, 0, 0, 255)
        + _s("red")
        + struct.pack("<HBBBB", 0, 0, 0, 255, 128),
    )
    tags = _chunk(
        0x2018,
        struct.pack("<H8x", 2)
        + struct.pack("<HHBH6xBBBx", 0, 1, 0, 0, 1, 2, 3)
        + _s("walk")
        + struct.pack("<HHBH6xBBBx", 1, 2, 2, 3, 0, 0, 0)
        + _s("idle"),
    )
    user = _chunk(0x2020, struct.pack("<I", 3) + _s("tag note") + struct.pack("<BBBB", 9, 8, 7, 6))
    sl = _chunk(
        0x2022,
        struct.pack("<III", 1, 3, 0)
        + _s("hitbox")
        + struct.pack("<IiiII", 0, 1, 2, 3, 4)
        + struct.pack("<iiII", 1, 1, 1, 1)
        + struct.pack("<ii", 2, 2),
    )
    unknown = _chunk(0x2007, struct.pack("<HHI8x", 1, 0, 0))  # color profile: sRGB, kept raw
    old_palette = _chunk(0x0004, struct.pack("<HBB", 1, 0, 2) + bytes([255, 0, 0, 0, 0, 255]))
    f0 = _frame(
        120,
        [
            unknown,
            old_palette,
            palette,
            _layer("bg"),
            _layer("group", ltype=1),
            _layer("hero", level=1, opacity=200),
            tags,
            user,
            sl,
            _cel(0, 0, 0, 0, _image(RGBA, compressed=False)),
            _cel(2, -1, 2, 2, _image(RGBA[:2, :3], compressed=True), opacity=128),
        ],
    )
    f1 = _frame(80, [_cel(0, 0, 0, 1, struct.pack("<H", 0)), _chunk(0x7777, b"future")])
    f2 = _frame(80, [])
    return _file(8, 6, 32, [f0, f1, f2])


def fixture_indexed() -> bytes:
    palette = _chunk(
        0x2019,
        struct.pack("<III8x", 4, 0, 3)
        + b"".join(struct.pack("<HBBBB", 0, v, v, v, 255) for v in (0, 80, 160, 240)),
    )
    f0 = _frame(100, [palette, _layer("ink"), _cel(0, 1, 1, 2, _image(INDEXED, compressed=True))])
    return _file(5, 4, 8, [f0], transparent=0)


def fixture_gray() -> bytes:
    f0 = _frame(50, [_layer("gray"), _cel(0, 0, 0, 0, _image(GRAY, compressed=False))])
    return _file(2, 1, 16, [f0])


FIXTURES = {"rgba": fixture_rgba, "indexed": fixture_indexed, "gray": fixture_gray}


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_roundtrip_fixture_files_semantically_equal(name: str, tmp_path: Path) -> None:
    path = tmp_path / f"{name}.aseprite"
    path.write_bytes(FIXTURES[name]())
    doc = ase.read_aseprite(path)
    out = tmp_path / f"{name}-out.aseprite"
    ase.write_aseprite(out, doc)
    again = ase.read_aseprite(out)
    aseprite_roundtrip_failures = 0 if again == doc else 1
    assert aseprite_roundtrip_failures == 0
    assert ase.serialize(again) == out.read_bytes()  # stable after the first rewrite


def test_reader_decodes_documented_fields() -> None:
    doc = ase.parse(fixture_rgba())
    assert (doc.width, doc.height, doc.depth, len(doc.frames)) == (8, 6, 32, 3)
    assert [f.duration for f in doc.frames] == [120, 80, 80]
    assert [(lay.name, lay.type, lay.child_level, lay.opacity) for lay in doc.layers()] == [
        ("bg", 0, 0, 255),
        ("group", 1, 0, 255),
        ("hero", 0, 1, 200),
    ]
    assert [(p.r, p.g, p.b, p.a, p.name) for p in doc.palette()] == [
        (255, 0, 0, 255, "red"),
        (0, 0, 255, 128, ""),
    ]
    assert [(t.name, t.start, t.end, t.direction, t.repeat) for t in doc.tags()] == [
        ("walk", 0, 1, 0, 0),
        ("idle", 1, 2, 2, 3),
    ]
    (sl,) = doc.slices()
    assert sl.name == "hitbox" and sl.keys[0].center == (1, 1, 1, 1) and sl.keys[0].pivot == (2, 2)
    raw_cel, packed_cel = doc.cels(0)
    np.testing.assert_array_equal(raw_cel.pixels, RGBA)
    np.testing.assert_array_equal(packed_cel.pixels, RGBA[:2, :3])
    assert (packed_cel.x, packed_cel.y, packed_cel.opacity) == (-1, 2, 128)
    (linked,) = doc.cels(1)
    assert (linked.kind, linked.link) == (ase.CEL_LINKED, 0)
    kinds = [c.type for c in doc.frames[0].chunks if isinstance(c, ase.RawChunk)]
    assert kinds == [0x2007, 0x0004]  # unknown and old chunks kept raw, in place
    assert isinstance(doc.frames[1].chunks[1], ase.RawChunk)
    ud = next(c for c in doc.frames[0].chunks if isinstance(c, ase.UserData))
    assert (ud.text, ud.color) == ("tag note", (9, 8, 7, 6))


def test_indexed_and_gray_pixels() -> None:
    np.testing.assert_array_equal(ase.parse(fixture_indexed()).cels(0)[0].pixels, INDEXED)
    np.testing.assert_array_equal(ase.parse(fixture_gray()).cels(0)[0].pixels, GRAY)


def test_bad_files_are_refused() -> None:
    with pytest.raises(ase.AsepriteError, match="magic"):
        ase.parse(b"\0" * 128)
    with pytest.raises(ase.AsepriteError, match="end of data"):
        ase.parse(fixture_rgba()[:200])


def test_written_document_from_scratch() -> None:
    doc = ase.AseDocument(4, 4, frames=[ase.Frame(100, [ase.Layer("a"), ase.Cel(0, pixels=RGBA)])])
    assert ase.parse(ase.serialize(doc)) == doc
    bad = ase.AseDocument(4, 4, depth=8, frames=[ase.Frame(100, [ase.Cel(0, pixels=RGBA)])])
    with pytest.raises(ase.AsepriteError, match="depth"):
        ase.serialize(bad)
