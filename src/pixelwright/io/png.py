"""PNG I/O: indexed (palette) PNGs to `IndexedImage`, everything else to `RGBImage`.

Transparency in an indexed PNG is written as one extra, last palette slot; transparent
pixels keep no colour index (they read back as index 0 with alpha False).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image as PILImage

from pixelwright.core.image import Image, IndexedImage, RGBImage
from pixelwright.core.palette import Color, Palette
from pixelwright.workspace.files import write_bytes_atomic


def read_png(path: Path) -> Image:
    with PILImage.open(path) as im:
        im.load()
        if im.mode == "P":
            return _from_paletted(im)
        return RGBImage(np.asarray(im.convert("RGBA"), dtype=np.uint8).copy())


def _from_paletted(im: PILImage.Image) -> IndexedImage:
    indices = np.asarray(im, dtype=np.uint8).astype(np.uint16)
    raw = im.getpalette() or [0, 0, 0]
    count = len(raw) // 3
    colors = [Color(raw[3 * i], raw[3 * i + 1], raw[3 * i + 2]) for i in range(count)]
    entry_alpha = np.full(count, 255, dtype=np.int32)
    trns = im.info.get("transparency")
    if isinstance(trns, int) and trns < count:
        entry_alpha[trns] = 0
    elif isinstance(trns, bytes):
        entry_alpha[: len(trns)] = list(trns[:count])
    alpha = entry_alpha[indices] > 0
    # pixelwright writes transparency as one extra, last palette slot: drop it again.
    if count > 1 and isinstance(trns, int) and trns == count - 1:
        colors = colors[:-1]
        indices = np.where(indices == trns, 0, indices).astype(np.uint16)
    return IndexedImage(indices, Palette(colors), None if alpha.all() else alpha)


def write_png(path: Path, image: Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        im, params = _to_pil(image)
        im.save(tmp, format="PNG", optimize=False, **params)
        write_bytes_atomic(path, tmp.read_bytes())
    finally:
        tmp.unlink(missing_ok=True)


def _to_pil(image: Image) -> tuple[PILImage.Image, dict[str, int]]:
    if isinstance(image, RGBImage):
        return PILImage.fromarray(image.rgba, mode="RGBA"), {}
    palette = image.palette
    indices = image.indices
    transparent = image.alpha is not None and not bool(image.alpha.all())
    entries = len(palette) + (1 if transparent else 0)
    if entries > 256:
        raise ValueError(f"indexed PNG holds at most 256 colors, need {entries}")
    flat = [v for c in palette for v in c.rgb]
    if transparent:
        assert image.alpha is not None
        slot = len(palette)
        flat += [0, 0, 0]
        indices = np.where(image.alpha, indices, slot).astype(np.uint16)
    im = PILImage.fromarray(indices.astype(np.uint8), mode="P")
    im.putpalette(flat or [0, 0, 0], rawmode="RGB")
    return im, ({"transparency": len(palette)} if transparent else {})
