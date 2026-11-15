"""In-memory images: `RGBImage` (generator output) and `IndexedImage` (palette indices)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from pixelwright.core.palette import Palette

U8 = npt.NDArray[np.uint8]
U16 = npt.NDArray[np.uint16]
Mask = npt.NDArray[np.bool_]


@dataclass(frozen=True, eq=False)
class RGBImage:
    """H x W x 4 uint8 RGBA pixels."""

    rgba: U8

    def __post_init__(self) -> None:
        if self.rgba.dtype != np.uint8 or self.rgba.ndim != 3 or self.rgba.shape[2] != 4:
            raise ValueError(f"expected H x W x 4 uint8, got {self.rgba.dtype} {self.rgba.shape}")

    @classmethod
    def from_array(cls, pixels: npt.ArrayLike) -> RGBImage:
        """Accept H x W x 3 (opaque) or H x W x 4 uint8-compatible arrays."""
        arr = np.asarray(pixels)
        if arr.ndim == 3 and arr.shape[2] == 3:
            alpha = np.full((*arr.shape[:2], 1), 255, dtype=np.uint8)
            arr = np.concatenate([arr.astype(np.uint8), alpha], axis=2)
        return cls(np.ascontiguousarray(arr, dtype=np.uint8))

    @property
    def height(self) -> int:
        return int(self.rgba.shape[0])

    @property
    def width(self) -> int:
        return int(self.rgba.shape[1])

    def to_rgba(self) -> U8:
        return self.rgba

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RGBImage) and np.array_equal(self.rgba, other.rgba)

    __hash__ = None  # type: ignore[assignment]


@dataclass(frozen=True, eq=False)
class IndexedImage:
    """H x W uint16 palette indices, a palette and an optional opacity mask (True = opaque)."""

    indices: U16
    palette: Palette
    alpha: Mask | None = None

    def __post_init__(self) -> None:
        if self.indices.dtype != np.uint16 or self.indices.ndim != 2:
            raise ValueError(
                f"expected H x W uint16, got {self.indices.dtype} {self.indices.shape}"
            )
        if self.indices.size and int(self.indices.max()) >= len(self.palette):
            raise ValueError("index outside the palette")
        if self.alpha is not None and (
            self.alpha.dtype != np.bool_ or self.alpha.shape != self.indices.shape
        ):
            raise ValueError("alpha must be a bool mask with the image's shape")

    @classmethod
    def from_array(
        cls, indices: npt.ArrayLike, palette: Palette, alpha: npt.ArrayLike | None = None
    ) -> IndexedImage:
        mask = None if alpha is None else np.asarray(alpha, dtype=np.bool_)
        return cls(np.ascontiguousarray(indices, dtype=np.uint16), palette, mask)

    @property
    def height(self) -> int:
        return int(self.indices.shape[0])

    @property
    def width(self) -> int:
        return int(self.indices.shape[1])

    def opaque(self) -> Mask:
        return np.ones(self.indices.shape, np.bool_) if self.alpha is None else self.alpha

    def to_rgba(self) -> U8:
        rgb = self.palette.rgb_array()[self.indices]
        a = np.where(self.opaque(), 255, 0).astype(np.uint8)[..., None]
        return np.concatenate([rgb, a], axis=2)

    def to_rgb_image(self) -> RGBImage:
        return RGBImage(self.to_rgba())

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, IndexedImage)
            and self.palette == other.palette
            and np.array_equal(self.indices, other.indices)
            and np.array_equal(self.opaque(), other.opaque())
        )

    __hash__ = None  # type: ignore[assignment]


Image = RGBImage | IndexedImage
