"""Palette quantization in OKLab (R-POST-2, R-POST-3).

Fixed mode maps every pixel to its nearest palette color in OKLab. Discovery builds a
palette with median cut or k-means in OKLab. Dithering is off everywhere except inside
an explicit mask, where a Bayer pattern mixes the two nearest palette colors.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from pixelwright.core.color import FloatArray, oklab_to_srgb8, srgb8_to_oklab
from pixelwright.core.image import IndexedImage, Mask, RGBImage
from pixelwright.core.palette import Color, Palette

ALPHA_THRESHOLD = 128
_CHUNK = 65536


@dataclass(frozen=True)
class QuantizeReport:
    mean_error: float  # mean OKLab distance of opaque pixels to their palette color
    max_error: float
    dithered_pixels: int


def bayer_matrix(size: int) -> FloatArray:
    """Normalized Bayer threshold matrix (values in (0, 1)), size a power of two."""
    if size < 2 or size & (size - 1):
        raise ValueError("Bayer size must be a power of two >= 2")
    m = np.array([[0, 2], [3, 1]], dtype=np.int64)
    while m.shape[0] < size:
        m = np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])
    return (m + 0.5) / (size * size)


def _two_nearest(lab: FloatArray, pal: FloatArray) -> tuple[npt.NDArray[np.intp], ...]:
    """Indices of the nearest and second-nearest palette colors for each row of `lab`."""
    first = np.empty(len(lab), dtype=np.intp)
    second = np.empty(len(lab), dtype=np.intp)
    for start in range(0, len(lab), _CHUNK):
        block = lab[start : start + _CHUNK]
        d = ((block[:, None, :] - pal[None, :, :]) ** 2).sum(axis=2)
        if pal.shape[0] == 1:
            first[start : start + len(block)] = 0
            second[start : start + len(block)] = 0
            continue
        part = np.argpartition(d, 1, axis=1)[:, :2]
        swap = d[np.arange(len(block)), part[:, 0]] > d[np.arange(len(block)), part[:, 1]]
        part[swap] = part[swap][:, ::-1]
        # Ties: prefer the lower palette index so results are stable.
        first[start : start + len(block)] = np.where(
            d[np.arange(len(block)), part[:, 0]] == d[np.arange(len(block)), part[:, 1]],
            part.min(axis=1),
            part[:, 0],
        )
        second[start : start + len(block)] = np.where(
            first[start : start + len(block)] == part[:, 0], part[:, 1], part[:, 0]
        )
    return first, second


def quantize_fixed(
    image: RGBImage,
    palette: Palette,
    *,
    dither_mask: Mask | None = None,
    bayer_size: int = 4,
) -> tuple[IndexedImage, QuantizeReport]:
    """Map `image` onto `palette` (nearest in OKLab); Bayer-dither only inside `dither_mask`."""
    if len(palette) == 0:
        raise ValueError("palette is empty")
    h, w = image.height, image.width
    if dither_mask is not None and dither_mask.shape != (h, w):
        raise ValueError("dither mask shape must match the image")
    rgb = image.rgba[..., :3].reshape(-1, 3)
    opaque = (image.rgba[..., 3] >= ALPHA_THRESHOLD).reshape(-1)
    uniq, inverse = np.unique(rgb, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    lab_u = srgb8_to_oklab(uniq)
    pal = palette.oklab()
    first_u, second_u = _two_nearest(lab_u, pal)
    index = first_u[inverse]

    dithered = 0
    if dither_mask is not None and dither_mask.any() and len(palette) > 1:
        c1, c2 = pal[first_u], pal[second_u]
        seg = c2 - c1
        denom = np.maximum((seg * seg).sum(axis=1), 1e-12)
        ratio_u = np.clip(((lab_u - c1) * seg).sum(axis=1) / denom, 0.0, 1.0)
        ys, xs = np.indices((h, w))
        thresh = bayer_matrix(bayer_size)[ys % bayer_size, xs % bayer_size].reshape(-1)
        use_second = dither_mask.reshape(-1) & (thresh < ratio_u[inverse])
        index = np.where(use_second, second_u[inverse], index)
        dithered = int((use_second & opaque).sum())

    err = np.sqrt(((srgb8_to_oklab(rgb[opaque]) - pal[index[opaque]]) ** 2).sum(axis=1))
    report = QuantizeReport(
        mean_error=float(err.mean()) if err.size else 0.0,
        max_error=float(err.max()) if err.size else 0.0,
        dithered_pixels=dithered,
    )
    indexed = IndexedImage(
        index.reshape(h, w).astype(np.uint16),
        palette,
        None if opaque.all() else opaque.reshape(h, w),
    )
    return indexed, report


ACCENT_BOOST = 40.0  # how much a fully important pixel outweighs a plain one
ACCENT_MIN = 0.5  # importance from which a pixel counts as an accent
ACCENT_DE = 0.06  # an accent this far (OKLab) from every palette colour gets its own
MAX_ACCENTS = 8  # palette entries added for accents, on top of `n`
MIN_SEPARATION = 0.03  # OKLab: palette entries closer than this are one colour (JPEG noise)
MIN_SEPARATION_RGB = 10.0  # ... or this close in sRGB 0-255: OKLab's cube root spreads near-blacks


def _weighted_colors(
    image: RGBImage, importance: FloatArray | None = None, scale: FloatArray | None = None
) -> tuple[FloatArray, FloatArray]:
    """Unique opaque colours in OKLab and their weights: pixel counts, each pixel boosted
    by `1 + ACCENT_BOOST * importance^2` when an importance map is given."""
    rgb = image.rgba[..., :3].reshape(-1, 3)
    opaque = (image.rgba[..., 3] >= ALPHA_THRESHOLD).reshape(-1)
    uniq, inverse = np.unique(rgb[opaque], axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    per_pixel = np.ones(len(inverse))
    if importance is not None:
        per_pixel += ACCENT_BOOST * importance.reshape(-1)[opaque] ** 2
    if scale is not None:
        per_pixel *= scale.reshape(-1)[opaque]
    weight = np.bincount(inverse, per_pixel, len(uniq))
    return srgb8_to_oklab(uniq), weight


def _best_split(
    lab: FloatArray, weight: FloatArray, box: npt.NDArray[np.intp]
) -> tuple[float, int, int]:
    """(error reduction, axis, cut) of the best variance-minimizing split of `box`."""
    best = (0.0, 0, 0)
    for axis in range(3):
        order = box[np.argsort(lab[box, axis], kind="stable")]
        w = weight[order][:, None]
        x = lab[order]
        cw, cx, cxx = np.cumsum(w, 0), np.cumsum(w * x, 0), np.cumsum(w * x * x, 0)
        tw, tx, txx = cw[-1], cx[-1], cxx[-1]
        lw, lx, lxx = cw[:-1], cx[:-1], cxx[:-1]
        left = (lxx - lx * lx / lw).sum(axis=1)
        right = ((txx - lxx) - (tx - lx) ** 2 / (tw - lw)).sum(axis=1)
        total = float((txx - tx * tx / tw).sum())
        k = int(np.argmin(left + right))
        gain = total - float(left[k] + right[k])
        if gain > best[0]:
            best = (gain, axis, k + 1)
    return best


def _median_cut(lab: FloatArray, weight: FloatArray, n: int) -> FloatArray:
    """Median-cut style box splitting; each split minimizes the weighted OKLab variance."""
    boxes = [np.arange(len(lab))]
    while len(boxes) < n:
        splits = [_best_split(lab, weight, b) if len(b) > 1 else (0.0, 0, 0) for b in boxes]
        target = int(np.argmax([sp[0] for sp in splits]))
        gain, axis, cut = splits[target]
        if gain <= 0:
            break
        box = boxes.pop(target)
        order = box[np.argsort(lab[box, axis], kind="stable")]
        boxes += [order[:cut], order[cut:]]
    return np.array([np.average(lab[b], axis=0, weights=weight[b]) for b in boxes])


def _kmeans(
    lab: FloatArray, weight: FloatArray, centers: FloatArray, iterations: int
) -> FloatArray:
    for _ in range(iterations):
        nearest, _second = _two_nearest(lab, centers)
        moved = centers.copy()
        for k in range(len(centers)):
            members = nearest == k
            if members.any():
                moved[k] = np.average(lab[members], axis=0, weights=weight[members])
        if np.allclose(moved, centers, atol=1e-6):
            return moved
        centers = moved
    return centers


def _merge_close(lab: FloatArray, weight: FloatArray, centers: FloatArray) -> FloatArray:
    """Merge palette entries closer than MIN_SEPARATION (weighted by the pixels they take).

    Large dark areas full of JPEG noise otherwise get several near-identical blacks; a
    1-pixel outline then splits between them, its pixels look like orphans and `clean`
    erases them."""
    while len(centers) > 1:
        d = np.sqrt(((centers[:, None] - centers[None, :]) ** 2).sum(axis=2))
        rgb = oklab_to_srgb8(centers).astype(np.float64)
        d_rgb = np.sqrt(((rgb[:, None] - rgb[None, :]) ** 2).sum(axis=2))
        close = (d < MIN_SEPARATION) | (d_rgb < MIN_SEPARATION_RGB)
        np.fill_diagonal(close, False)
        if not close.any():
            break
        d = np.where(close, d, np.inf)
        i, j = np.unravel_index(int(np.argmin(d)), d.shape)
        nearest, _second = _two_nearest(lab, centers)
        wi, wj = weight[nearest == i].sum(), weight[nearest == j].sum()
        merged = (centers[i] * wi + centers[j] * wj) / max(wi + wj, 1e-12)
        centers = np.vstack([np.delete(centers, [i, j], axis=0), merged])
    return centers


def _add_accents(image: RGBImage, importance: FloatArray, centers: FloatArray) -> FloatArray:
    """Append up to MAX_ACCENTS colours for important pixels the palette misses."""
    opaque = (image.rgba[..., 3] >= ALPHA_THRESHOLD).reshape(-1)
    imp = importance.reshape(-1)[opaque]
    lab = srgb8_to_oklab(image.rgba[..., :3].reshape(-1, 3)[opaque])
    keep = imp >= ACCENT_MIN
    lab, imp = lab[keep], imp[keep]
    for _ in range(MAX_ACCENTS):
        if len(lab) == 0:
            break
        nearest, _second = _two_nearest(lab, centers)
        far = np.sqrt(((lab - centers[nearest]) ** 2).sum(axis=1)) > ACCENT_DE
        if not far.any():
            break
        lab, imp = lab[far], imp[far]
        # the densest missed colour, by importance: the heaviest of a few median-cut boxes
        boxes = _median_cut(lab, imp, min(4, len(lab)))
        group, _ = _two_nearest(lab, boxes)
        heaviest = int(np.argmax(np.bincount(group, imp, len(boxes))))
        centers = np.vstack([centers, boxes[heaviest]])
    return centers


def discover_palette(
    image: RGBImage,
    n: int,
    *,
    method: str = "kmeans",
    iterations: int = 20,
    importance: FloatArray | None = None,
    scale: FloatArray | None = None,
) -> Palette:
    """Build a palette of at most `n` colors for `image` (median cut, refined by k-means).

    With an `importance` map (`core.importance.importance_map`), small colours that stand
    out locally (lights, eyes, accents) weigh more, and any of them still far from every
    entry gets its own (up to MAX_ACCENTS more than `n`). `scale` multiplies each pixel's
    weight (several images side by side, each made to count the same)."""
    if n < 1:
        raise ValueError("n must be >= 1")
    if method not in ("kmeans", "median-cut"):
        raise ValueError("method must be 'kmeans' or 'median-cut'")
    lab, weight = _weighted_colors(image, importance, scale)
    if len(lab) == 0:
        raise ValueError("image has no opaque pixels")
    centers = _median_cut(lab, weight, n)
    if method == "kmeans":
        centers = _kmeans(lab, weight, centers, iterations)
    centers = _merge_close(lab, weight, centers)
    if importance is not None:
        centers = _add_accents(image, importance, centers)
    order = np.argsort(centers[:, 0], kind="stable")  # dark to light
    seen: list[tuple[int, int, int]] = []
    for rgb in oklab_to_srgb8(centers[order]):
        t = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        if t not in seen:
            seen.append(t)
    return Palette([Color(*t) for t in seen])
