"""`snap`: recover the pixel grid of pseudo-pixel art and downsample it to native size.

Scale and offset: color changes happen on cell borders, so the peaks of the edge-energy
profile along each axis sit on a regular grid; the largest scale that explains them
(see `detect_grid`) and its phase are the grid. Each cell becomes the
per-channel median of its inner region, robust to blur, JPEG and noise at the borders.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

import numpy as np
import numpy.typing as npt

from pixelwright.core.image import RGBImage

F64 = npt.NDArray[np.float64]
MIN_SCALE = 2
MAX_SCALE = 16
PEAK_FLOOR = 0.15  # peaks below this share of the strongest one are ignored
JITTER_TOLERANCE = 0.15  # a peak may sit this fraction of a cell off its grid line
FIT_MARGIN = 0.08
INNER_REL = 1.3
INNER_ABS = 2.0  # RMS, 0-255 units
MULTIPLE_KEEP = 0.8  # a multiple of the pick keeping this share of its raw on-grid weight wins


@dataclass(frozen=True)
class SnapResult:
    image: RGBImage  # native resolution, one pixel per detected cell
    scale: int
    offset: tuple[int, int]  # (x, y) phase of the grid lines, in source pixels
    confidence: float  # 0-1: how clearly the chosen scale beats the next coarser one
    fits: dict[int, float]  # share of border energy on the grid, per candidate scale


def _median3(rgb: F64) -> F64:
    """3x3 median filter: removes noise and JPEG ringing, keeps step edges in place."""
    pad = np.pad(rgb, ((1, 1), (1, 1), (0, 0)), mode="edge")
    h, w = rgb.shape[:2]
    stack = [pad[dy : dy + h, dx : dx + w] for dy in range(3) for dx in range(3)]
    return np.median(np.stack(stack), axis=0)


def _edge_profile(rgb: F64, axis: int) -> F64:
    """Energy of the color change between pixel i-1 and i along `axis` (index i)."""
    diff = np.abs(np.diff(rgb, axis=axis)).sum(axis=2)
    profile = diff.sum(axis=1 - axis)
    return np.concatenate([[0.0], profile])


def _peaks(profile: F64) -> tuple[npt.NDArray[np.intp], F64]:
    """Positions and weights of border peaks: local maxima of the smoothed profile."""
    smooth = np.convolve(profile, [1.0, 2.0, 1.0], mode="same")
    if smooth.max() <= 0:
        return np.array([], dtype=np.intp), np.array([])
    left = np.concatenate([[-np.inf], smooth[:-1]])
    right = np.concatenate([smooth[1:], [-np.inf]])
    is_peak = (smooth > left) & (smooth >= right) & (smooth >= PEAK_FLOOR * smooth.max())
    pos = np.flatnonzero(is_peak)
    return pos, smooth[pos]


def _tolerance(scale: int) -> float:
    return max(0.6, JITTER_TOLERANCE * scale)


def _fit(
    pos: npt.NDArray[np.intp], weight: F64, scale: int, tol: float | None = None
) -> tuple[float, int, float]:
    """(chance-normalized share of peak weight on a grid of this scale, best phase, raw share)."""
    if weight.sum() <= 0:
        return 0.0, 0, 0.0
    tol = _tolerance(scale) if tol is None else tol
    best, phase = -1.0, 0
    for p in range(scale):
        d = np.abs((pos - p + scale / 2) % scale - scale / 2)
        score = float(weight[d <= tol].sum())
        if score > best:
            best, phase = score, p
    share = best / float(weight.sum())
    # Normalize against chance: a wide tolerance on a coarse grid catches random peaks too.
    r = np.arange(scale)
    chance = float((np.abs((r + scale / 2) % scale - scale / 2) <= tol).mean())
    return (share - chance) / (1.0 - chance) if chance < 1 else 0.0, phase, share


def _phase(profile: F64, scale: int) -> int:
    pos, weight = _peaks(profile)
    return _fit(pos, weight, scale)[1]


def _cell_bounds(n: int, scale: int, phase: int) -> list[tuple[int, int]]:
    """Cells between grid lines at positions == phase (mod scale); slivers < scale/2 dropped."""
    lines = list(range(phase, n + 1, scale))
    if not lines or lines[0] != 0:
        lines = [0, *lines]
    if lines[-1] != n:
        lines.append(n)
    cells = list(pairwise(lines))
    return [(a, b) for a, b in cells if b - a >= max(1, scale / 2)]


def _inner(a: int, b: int, scale: int) -> tuple[int, int]:
    inset = int((b - a) * 0.25) if scale >= 4 else 0
    return a + inset, b - inset


def _downsample(rgb: F64, scale: int, phase_x: int, phase_y: int) -> F64:
    """One value per cell (H' x W' x 3): the per-channel median of the cell's inner region."""
    rows = _cell_bounds(rgb.shape[0], scale, phase_y)
    cols = _cell_bounds(rgb.shape[1], scale, phase_x)
    cells = np.empty((len(rows), len(cols), 3))
    for i, (y0, y1) in enumerate(rows):
        iy0, iy1 = _inner(y0, y1, scale)
        band = rgb[iy0:iy1]
        for j, (x0, x1) in enumerate(cols):
            ix0, ix1 = _inner(x0, x1, scale)
            value = np.median(band[:, ix0:ix1].reshape(-1, 3), axis=0)
            cells[i, j] = value
    return cells


def _inner_error(rgb: F64, scale: int, px: int, py: int) -> float:
    """RMS deviation of the inner region of each full cell from that region's mean."""
    y0 = py if py else 0
    x0 = px if px else 0
    ny, nx = (rgb.shape[0] - y0) // scale, (rgb.shape[1] - x0) // scale
    if ny < 1 or nx < 1:
        return float("inf")
    blocks = rgb[y0 : y0 + ny * scale, x0 : x0 + nx * scale].reshape(ny, scale, nx, scale, 3)
    inset = scale // 4
    inner = blocks[:, inset : scale - inset, :, inset : scale - inset, :]
    dev = inner - inner.mean(axis=(1, 3), keepdims=True)
    return float(np.sqrt((dev**2).mean()))


def detect_grid(
    image: RGBImage, max_scale: int = MAX_SCALE
) -> tuple[int, int, int, float, dict[int, float]]:
    """(scale, phase_x, phase_y, confidence, fit per scale) for `image`.

    Border peaks of both axes must sit on the grid; every divisor of the true scale fits
    as well as the scale itself and multiples fit about half, so the largest scale whose
    fit is within `FIT_MARGIN` of the best wins.
    """
    rgb = image.rgba[..., :3].astype(np.float64)
    h, w = rgb.shape[:2]
    top = min(max_scale, min(h, w) // 4)
    if top < MIN_SCALE:
        return 1, 0, 0, 0.0, {}
    # Two views of the borders: the median-filtered image (robust to noise and JPEG) and
    # the raw one (keeps 2-3 px cells the median filter erodes); each scale takes the
    # better fit of the two.
    views = []
    for src in (_median3(rgb), rgb):
        pos_x, w_x = _peaks(_edge_profile(src, 1))
        pos_y, w_y = _peaks(_edge_profile(src, 0))
        views.append((pos_x, w_x, pos_y, w_y))
    fits: dict[int, float] = {}
    raw: dict[int, float] = {}
    phases: dict[int, tuple[int, int]] = {}
    for s in range(MIN_SCALE, top + 1):
        fits[s] = -1.0
        for pos_x, w_x, pos_y, w_y in views:
            total = float(w_x.sum() + w_y.sum())
            if total <= 0:
                continue
            fx, ox, rx = _fit(pos_x, w_x, s)
            fy, oy, ry = _fit(pos_y, w_y, s)
            f = (fx * float(w_x.sum()) + fy * float(w_y.sum())) / total
            if f > fits[s]:
                fits[s], phases[s] = f, (ox, oy)
                raw[s] = (rx * float(w_x.sum()) + ry * float(w_y.sum())) / total
    if max(fits.values()) <= 0:
        return 1, 0, 0, 0.0, {}
    best = max(fits.values())
    candidates = [s for s, f in fits.items() if f >= best - FIT_MARGIN]
    # Coarse scales can fit the border peaks by coincidence; their cells then straddle
    # real borders, which shows as variation inside the cells' inner regions.
    inner = {s: _inner_error(rgb, s, *phases[s]) for s in candidates}
    floor = min(inner.values())
    limit = floor * INNER_REL + INNER_ABS
    scale = max(s for s in candidates if inner[s] <= limit)
    # With many off-grid peaks (noise, gradients) chance normalization favors divisors of
    # the true scale. A multiple of a wrong divisor keeps about half of its on-grid peaks;
    # the true scale keeps nearly all of them.
    multiples = [m for m in fits if m > scale > MIN_SCALE and m % scale == 0]
    for m in sorted(multiples, reverse=True):
        if raw.get(m, 0.0) >= MULTIPLE_KEEP * raw[scale] and (
            _inner_error(rgb, m, *phases[m]) <= limit
        ):
            scale = m
            break
    coarser = [f for s, f in fits.items() if s > scale and s % scale == 0]
    gap = fits[scale] - (max(coarser) if coarser else 0.5)
    confidence = float(np.clip(fits[scale] * min(1.0, gap / 0.4), 0.0, 1.0))
    return scale, phases[scale][0], phases[scale][1], confidence, fits


def snap(image: RGBImage, *, scale: int | None = None, max_scale: int = MAX_SCALE) -> SnapResult:
    """Detect (or use the given) scale and downsample `image` to one pixel per cell."""
    rgb = image.rgba[..., :3].astype(np.float64)
    if scale is None:
        scale, px, py, confidence, fits = detect_grid(image, max_scale)
    else:
        if scale < 1:
            raise ValueError("scale must be >= 1")
        px = _phase(_edge_profile(rgb, 1), scale) if scale > 1 else 0
        py = _phase(_edge_profile(rgb, 0), scale) if scale > 1 else 0
        confidence, fits = 1.0, {}
    if scale <= 1:
        return SnapResult(image, 1, (0, 0), confidence, fits)
    cells = _downsample(rgb, scale, px, py)
    out = np.clip(np.rint(cells), 0, 255).astype(np.uint8)
    return SnapResult(RGBImage.from_array(out), scale, (px, py), confidence, fits)
