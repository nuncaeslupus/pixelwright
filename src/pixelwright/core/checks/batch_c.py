"""Checks batch C beyond `pillow`: ramps, dither-zones, aa, selout, outline-share,
depth-falloff, figure-ground, diagnostics."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise

import numpy as np
import numpy.typing as npt

from pixelwright.core.checks.base import Box, CheckResult, tile_boxes
from pixelwright.core.checks.line_runs import line_components
from pixelwright.core.checks.shape import boundary, erode, ring, subject_mask
from pixelwright.core.color import oklab_to_oklch, srgb8_to_oklab
from pixelwright.core.image import Image, IndexedImage, Mask
from pixelwright.core.palette import Palette, Ramps, analyze_ramp
from pixelwright.core.render import lightness

F64 = npt.NDArray[np.float64]


def check_ramps(
    palette: Palette,
    ramps: Ramps,
    hue_band: tuple[float, float] = (5.0, 30.0),
    min_step: float = 0.03,
) -> CheckResult:
    """`ramps` (R-PIX-2): L rises, adjacent hue shift in band (chromatic steps), no flat steps."""
    problems: dict[str, list[str]] = {}
    for name, ramp in ramps.ramps.items():
        rep = analyze_ramp(palette, ramp)
        issues = []
        if not rep.monotonic_lightness:
            issues.append("lightness not monotonic")
        if min(np.diff(rep.lightness), default=1.0) < min_step:
            issues.append("flat step")
        for i in range(len(rep.hue) - 1):
            if min(rep.chroma[i], rep.chroma[i + 1]) < 0.02:
                continue  # hue is meaningless on near-grays
            dh = abs((rep.hue[i + 1] - rep.hue[i] + 180) % 360 - 180)
            if not hue_band[0] <= dh <= hue_band[1]:
                issues.append(f"hue step {i}: {dh:.1f} deg")
        if issues:
            problems[name] = issues
    return CheckResult(
        "ramps",
        "R-PIX-2",
        "warn" if problems else "pass",
        float(len(problems)),
        0.0,
        (),
        {"problems": problems},
    )


def checker_mask(image: IndexedImage) -> Mask:
    """Pixels in a 1x1 checkerboard: unlike all 4 orthogonal neighbours, like all 4 diagonals."""
    k = np.where(image.opaque(), image.indices.astype(np.int64), -1)
    p = np.pad(k, 1, constant_values=-2)
    h, w = k.shape

    def at(dy: int, dx: int) -> npt.NDArray[np.int64]:
        return p[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]

    ortho = (at(-1, 0) != k) & (at(1, 0) != k) & (at(0, -1) != k) & (at(0, 1) != k)
    diag = (at(-1, -1) == k) & (at(-1, 1) == k) & (at(1, -1) == k) & (at(1, 1) == k)
    out: Mask = ortho & diag & image.opaque()
    return out


def check_dither_zones(
    image: IndexedImage, zones: Mask | None = None, min_pixels: int = 4
) -> CheckResult:
    """`dither-zones` (R-PIX-7): ordered dither patterns outside the declared zones."""
    pattern = checker_mask(image)
    allowed = np.zeros_like(pattern) if zones is None else zones
    outside = pattern & ~allowed
    boxes = tuple(
        b
        for b in tile_boxes(outside, 8)
        if outside[b[1] : b[1] + b[3], b[0] : b[0] + b[2]].sum() >= min_pixels
    )
    return CheckResult(
        "dither-zones",
        "R-PIX-7",
        "warn" if boxes else "pass",
        float(outside.sum()),
        0.0,
        boxes,
        {"inside_zones": int((pattern & allowed).sum())},
    )


def check_aa(image: IndexedImage) -> CheckResult:
    """`aa` (R-PIX-8): edge pixels of a sprite whose lightness sits between the outline color
    and the inner color, i.e. anti-aliasing against an unknown background."""
    mask = image.opaque()
    if mask.all():
        return CheckResult("aa", "R-PIX-8", "pass", 0.0, 0.0, (), {"reason": "no alpha boundary"})
    edge = boundary(mask)
    light = image.palette.oklab()[:, 0][image.indices]
    edge_idx = image.indices[edge]
    if edge_idx.size == 0:
        return CheckResult("aa", "R-PIX-8", "pass", 0.0, 0.0)
    outline = int(np.bincount(edge_idx).argmax())
    inner = mask & ~edge
    inner_l = float(light[inner].mean()) if inner.any() else float(light[mask].mean())
    lo, hi = sorted((float(image.palette.oklab()[outline, 0]), inner_l))
    aa = edge & (image.indices != outline) & (light > lo + 0.02) & (light < hi - 0.02)
    return CheckResult(
        "aa",
        "R-PIX-8",
        "warn" if aa.any() else "pass",
        float(aa.sum()),
        0.0,
        tile_boxes(aa, 8),
        {"outline_index": outline},
    )


def check_selout(image: Image) -> CheckResult:
    """`selout` (R-PIX-9, report): outline vs inner neighbour lightness/hue, pure-black share."""
    mask = subject_mask(image)
    edge = boundary(mask)
    rgba = image.to_rgba()
    lab = srgb8_to_oklab(rgba[..., :3])
    inner = erode(mask)
    if not edge.any() or not inner.any():
        return CheckResult("selout", "R-PIX-9", "pass", 0.0, None, (), {"reason": "no outline"})
    inner_mean = lab[inner].mean(axis=0)
    edge_lab = lab[edge]
    black = (rgba[..., :3][edge] < 16).all(axis=1)
    lch_e, lch_i = oklab_to_oklch(edge_lab.mean(axis=0)), oklab_to_oklch(inner_mean)
    return CheckResult(
        "selout",
        "R-PIX-9",
        "pass",
        float(black.mean()),
        None,
        (),
        {
            "delta_l": float(inner_mean[0] - edge_lab[:, 0].mean()),
            "hue_delta": float(abs((lch_e[2] - lch_i[2] + 180) % 360 - 180)),
            "pure_black_share": float(black.mean()),
        },
    )


def check_outline_share(image: IndexedImage, dark: float = 0.25) -> CheckResult:
    """`outline-share` (R-STYLE-4, report): share of pixels in dark 1-px strokes."""
    light = image.palette.oklab()[:, 0]
    strokes = np.zeros(image.indices.shape, dtype=bool)
    for comp in line_components(image):
        if light[int(image.indices[comp][0])] < dark:
            strokes |= comp
    share = float(strokes.sum() / max(image.opaque().sum(), 1))
    return CheckResult(
        "outline-share", "R-STYLE-4", "pass", share, None, (), {"pixels": int(strokes.sum())}
    )


def check_depth_falloff(image: Image, layers: Sequence[Mask]) -> CheckResult:
    """`depth-falloff` (R-DEPTH-1): contrast and distance to the farthest layer's color must
    fall from near (first) to far (last)."""
    lab = srgb8_to_oklab(image.to_rgba()[..., :3])
    used = [m for m in layers if m.any()]
    if len(used) < 2:
        return CheckResult(
            "depth-falloff", "R-DEPTH-1", "pass", 0.0, None, (), {"reason": "< 2 layers"}
        )
    sky = lab[used[-1]].mean(axis=0)
    contrast = [float(lab[m][:, 0].std()) for m in used]
    distance = [float(np.linalg.norm(lab[m].mean(axis=0) - sky)) for m in used]
    ok = all(a >= b - 1e-6 for a, b in pairwise(contrast)) and all(
        a >= b - 1e-6 for a, b in pairwise(distance)
    )
    return CheckResult(
        "depth-falloff",
        "R-DEPTH-1",
        "pass" if ok else "warn",
        float(ok),
        1.0,
        (),
        {"contrast": contrast, "distance_to_far": distance},
    )


def check_figure_ground(image: Image, sprite: Mask, min_delta: float = 0.1) -> CheckResult:
    """`figure-ground` (R-COLOR-1): lightness gap between a sprite and the pixels around it."""
    light = lightness(image.to_rgba())
    around = ring(sprite, 3)
    if not sprite.any() or not around.any():
        return CheckResult(
            "figure-ground", "R-COLOR-1", "pass", 0.0, min_delta, (), {"reason": "empty"}
        )
    delta = abs(float(light[boundary(sprite)].mean()) - float(light[around].mean()))
    ys, xs = np.nonzero(sprite)
    box: Box = (int(xs.min()), int(ys.min()), int(np.ptp(xs)) + 1, int(np.ptp(ys)) + 1)
    low = delta < min_delta
    return CheckResult(
        "figure-ground",
        "R-COLOR-1",
        "warn" if low else "pass",
        delta,
        min_delta,
        (box,) if low else (),
    )


def check_diagnostics(image: Image, focal: Mask | None = None) -> CheckResult:
    """`diagnostics` (DA-Q001-2, report): contrast-saliency peak vs focal mask, spectrum slope."""
    light = lightness(image.to_rgba())
    h, w = light.shape
    spec = np.abs(np.fft.fftshift(np.fft.fft2(light - light.mean()))) ** 2
    yy, xx = np.indices((h, w))
    r = np.hypot(yy - h // 2, xx - w // 2).astype(int)
    radial = np.bincount(r.ravel(), spec.ravel()) / np.maximum(np.bincount(r.ravel()), 1)
    freqs = np.arange(1, min(h, w) // 2)
    slope = (
        float(np.polyfit(np.log(freqs), np.log(radial[freqs] + 1e-12), 1)[0])
        if len(freqs) > 2
        else 0.0
    )
    pad = np.pad(light, 2, mode="edge")
    local = np.zeros_like(light)
    for dy in range(5):
        for dx in range(5):
            local += (pad[dy : dy + h, dx : dx + w] - light) ** 2
    peak_y, peak_x = divmod(int(np.argmax(local)), w)
    in_focal = bool(focal[peak_y, peak_x]) if focal is not None else None
    return CheckResult(
        "diagnostics",
        "DA-Q001-2",
        "pass",
        slope,
        None,
        (),
        {"spectrum_slope": slope, "saliency_peak": [peak_x, peak_y], "peak_in_focal": in_focal},
    )
