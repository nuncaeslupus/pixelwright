"""Turn a painting into pixels that each do something.

A painting reduced to a small canvas keeps its brush texture as scattered pixels: grass
and paths become noise instead of shapes. Two steps fix most of it:

- `kuwahara` flattens texture while keeping edges, before the image is reduced;
- `remove_small_clusters` folds same-colour groups of a few pixels into their
  surroundings after the palette is applied, except pixels marked as protected
  (accents: a lit window, a star).
"""

from __future__ import annotations

from collections import Counter

import numpy as np
import numpy.typing as npt

from pixelwright.core.image import IndexedImage, Mask

F64 = npt.NDArray[np.float64]


def _box_sums(a: F64, r: int) -> F64:
    """Sum over each (r+1)x(r+1) window whose top-left corner is the pixel (edges clamped)."""
    h, w = a.shape[:2]
    pad = np.pad(a, ((1, r), (1, r)) + ((0, 0),) * (a.ndim - 2), mode="edge")
    sat = pad.cumsum(0).cumsum(1)
    k = r + 1
    out: F64 = sat[k : k + h, k : k + w] - sat[:h, k : k + w] - sat[k : k + h, :w] + sat[:h, :w]
    return out


def kuwahara(rgb: F64, radius: int) -> F64:
    """Edge-preserving smoothing: each pixel takes the mean of whichever of its four
    (radius+1)^2 quadrants has the least variance, so flat areas flatten and edges stay."""
    if radius < 1:
        return rgb
    h, w = rgb.shape[:2]
    n = float((radius + 1) ** 2)
    pad = np.pad(rgb, ((radius, radius), (radius, radius), (0, 0)), mode="edge")
    sums = _box_sums(pad, radius)
    sq = _box_sums((pad**2).sum(axis=2), radius)
    best_var = np.full((h, w), np.inf)
    out = np.empty_like(rgb)
    for dy in (0, radius):  # quadrant top-left offsets within the padded image
        for dx in (0, radius):
            s = sums[dy : dy + h, dx : dx + w]
            mean = s / n
            var = sq[dy : dy + h, dx : dx + w] / n - (mean**2).sum(axis=2)
            better = var < best_var
            best_var = np.where(better, var, best_var)
            out[better] = mean[better]
    return out


def _components(key: npt.NDArray[np.int64]) -> tuple[npt.NDArray[np.int64], list[int]]:
    """8-connected same-colour components: (label per pixel, size per label)."""
    h, w = key.shape
    labels = np.full((h, w), -1, np.int64)
    sizes: list[int] = []
    flat = key.ravel()
    lab = labels.ravel()
    for start in range(h * w):
        if lab[start] >= 0:
            continue
        current = len(sizes)
        lab[start] = current
        stack, size, colour = [start], 0, flat[start]
        while stack:
            p = stack.pop()
            size += 1
            y, x = divmod(p, w)
            for ny in (y - 1, y, y + 1):
                if ny < 0 or ny >= h:
                    continue
                for nx in (x - 1, x, x + 1):
                    if 0 <= nx < w:
                        q = ny * w + nx
                        if lab[q] < 0 and flat[q] == colour:
                            lab[q] = current
                            stack.append(q)
        sizes.append(size)
    return labels, sizes


def remove_small_clusters(
    image: IndexedImage, max_size: int = 4, protect: Mask | None = None, passes: int = 2
) -> tuple[IndexedImage, int]:
    """Recolour same-colour groups of at most `max_size` pixels with the colour most
    common around them. Groups touching a protected pixel are kept. Returns the image and
    how many pixels changed."""
    key = image.indices.astype(np.int64).copy()
    opaque = image.opaque()
    key[~opaque] = -1
    h, w = key.shape
    changed = 0
    for _ in range(passes):
        labels, sizes = _components(key)
        small = [i for i, s in enumerate(sizes) if s <= max_size]
        if not small:
            break
        smalls = set(small)
        members: dict[int, list[tuple[int, int]]] = {}
        for y, x in zip(*np.nonzero(np.isin(labels, small)), strict=True):
            members.setdefault(int(labels[y, x]), []).append((int(y), int(x)))
        snapshot = key.copy()
        for label, pixels in members.items():
            if key[pixels[0]] < 0 or (protect is not None and any(protect[p] for p in pixels)):
                continue
            around: Counter[int] = Counter()
            for y, x in pixels:
                for ny in range(max(0, y - 1), min(h, y + 2)):
                    for nx in range(max(0, x - 1), min(w, x + 2)):
                        other = int(labels[ny, nx])
                        if other != label and other not in smalls and snapshot[ny, nx] >= 0:
                            around[int(snapshot[ny, nx])] += 1
            if around:
                colour = around.most_common(1)[0][0]
                for p in pixels:
                    key[p] = colour
                changed += len(pixels)
    indices = np.where(key < 0, image.indices, key).astype(image.indices.dtype)
    return IndexedImage(indices, image.palette, image.alpha), changed


def small_cluster_share(image: IndexedImage, max_size: int = 4) -> float:
    """Share of pixels in same-colour groups of at most `max_size` pixels."""
    labels, sizes = _components(image.indices.astype(np.int64))
    per_pixel = np.asarray(sizes)[labels]
    return float((per_pixel <= max_size).mean())
