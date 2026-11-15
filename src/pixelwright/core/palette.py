"""Palette and ramp model."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from pixelwright.core.color import FloatArray, oklab_to_oklch, srgb8_to_oklab


@dataclass(frozen=True)
class Color:
    """An 8-bit sRGB color with an optional name."""

    r: int
    g: int
    b: int
    name: str = ""

    def __post_init__(self) -> None:
        for channel in (self.r, self.g, self.b):
            if not 0 <= channel <= 255:
                raise ValueError(f"channel out of range 0-255: {channel}")

    @property
    def rgb(self) -> tuple[int, int, int]:
        return (self.r, self.g, self.b)

    @property
    def hex(self) -> str:
        return f"{self.r:02x}{self.g:02x}{self.b:02x}"

    @classmethod
    def from_hex(cls, value: str, name: str = "") -> Color:
        text = value.strip().removeprefix("#")
        if len(text) != 6:
            raise ValueError(f"expected RRGGBB, got {value!r}")
        try:
            r, g, b = (int(text[i : i + 2], 16) for i in (0, 2, 4))
        except ValueError as exc:
            raise ValueError(f"expected RRGGBB, got {value!r}") from exc
        return cls(r, g, b, name)


@dataclass(frozen=True)
class Palette:
    """An ordered list of colors; the index of a color is its palette index."""

    colors: tuple[Color, ...]
    name: str = ""
    columns: int = 0

    def __init__(self, colors: Iterable[Color], name: str = "", columns: int = 0) -> None:
        object.__setattr__(self, "colors", tuple(colors))
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "columns", columns)
        if len(self.colors) > 65536:
            raise ValueError("a palette holds at most 65536 colors")

    def __len__(self) -> int:
        return len(self.colors)

    def __iter__(self) -> Iterator[Color]:
        return iter(self.colors)

    def __getitem__(self, index: int) -> Color:
        return self.colors[index]

    def rgb_array(self) -> npt.NDArray[np.uint8]:
        """N x 3 uint8 array in palette order."""
        return np.array([c.rgb for c in self.colors], dtype=np.uint8).reshape(-1, 3)

    def oklab(self) -> FloatArray:
        """N x 3 OKLab coordinates in palette order."""
        return srgb8_to_oklab(self.rgb_array())

    def index_of(self, color: Color | tuple[int, int, int]) -> int:
        rgb = color.rgb if isinstance(color, Color) else tuple(color)
        for i, c in enumerate(self.colors):
            if c.rgb == rgb:
                return i
        raise KeyError(f"color not in palette: {rgb}")


@dataclass(frozen=True)
class Ramp:
    """A material ramp: palette indices from dark to light."""

    indices: tuple[int, ...]
    cycle: bool = False
    note: str = ""

    def __post_init__(self) -> None:
        if len(self.indices) < 2:
            raise ValueError("a ramp needs at least two colors")
        if len(set(self.indices)) != len(self.indices):
            raise ValueError(f"ramp repeats an index: {self.indices}")


@dataclass
class Ramps:
    """Named ramps over one palette (`ramps.yaml`)."""

    ramps: dict[str, Ramp] = field(default_factory=dict)
    palette: str = ""  # palette file the indices refer to, relative to the ramps file

    def check_against(self, palette: Palette) -> None:
        for name, ramp in self.ramps.items():
            bad = [i for i in ramp.indices if not 0 <= i < len(palette)]
            if bad:
                raise ValueError(f"ramp {name!r}: indices out of palette range: {bad}")


@dataclass(frozen=True)
class RampReport:
    """OKLCH profile of a ramp, dark to light."""

    lightness: tuple[float, ...]
    chroma: tuple[float, ...]
    hue: tuple[float, ...]
    monotonic_lightness: bool
    hue_shift_deg: float  # signed hue change from the darkest to the lightest step


def analyze_ramp(palette: Palette, ramp: Ramp | Sequence[int]) -> RampReport:
    indices = ramp.indices if isinstance(ramp, Ramp) else tuple(ramp)
    lch = oklab_to_oklch(palette.oklab()[list(indices)])
    lightness = lch[:, 0]
    shift = float((lch[-1, 2] - lch[0, 2] + 180.0) % 360.0 - 180.0)
    return RampReport(
        lightness=tuple(float(v) for v in lightness),
        chroma=tuple(float(v) for v in lch[:, 1]),
        hue=tuple(float(v) for v in lch[:, 2]),
        monotonic_lightness=bool(np.all(np.diff(lightness) > 0)),
        hue_shift_deg=shift,
    )


# OKLCH hue bands (degrees, upper bounds); pure sRGB red sits near 29, blue near 264.
FAMILIES = (
    (45.0, "red"),
    (80.0, "orange"),
    (125.0, "yellow"),
    (175.0, "green"),
    (230.0, "cyan"),
    (300.0, "blue"),
    (350.0, "magenta"),
    (360.0, "red"),
)


def hue_family(hue: float) -> str:
    return next(name for top, name in FAMILIES if hue % 360.0 < top)


def propose_ramps(palette: Palette, neutral_chroma: float = 0.03) -> Ramps:
    """Group colors into hue families (OKLCH bands, plus neutrals) and order each dark
    to light. Families with fewer than two colors get no ramp."""
    lch = oklab_to_oklch(palette.oklab())
    groups: dict[str, list[int]] = {}
    for i, (_, chroma, hue) in enumerate(lch):
        family = "neutral" if chroma < neutral_chroma else hue_family(float(hue))
        groups.setdefault(family, []).append(i)
    ramps = {
        name: Ramp(tuple(sorted(members, key=lambda i: float(lch[i, 0]))))
        for name, members in groups.items()
        if len(members) >= 2
    }
    return Ramps(ramps)
