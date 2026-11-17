"""The game's style kit: what every generated image must follow, in one place.

A kit is the palette and canvas of the asset's settings, plus `[style]` in
`pixelwright.toml` (a `preamble` and a list of pixel `rules`, overridden per category by
`[style.<category>]`) and the reference images in `style/references/` (and
`style/references/<category>/`). `pw generate` sends all of it with every prompt and
normalise uses the same palette and canvas, so what comes back is already in style.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pixelwright.asset import Asset
from pixelwright.io.palette_io import read_palette
from pixelwright.project import Project, ProjectError

REFERENCES_DIR = Path("style") / "references"
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


@dataclass(frozen=True)
class StyleKit:
    category: str
    palette: str
    colors: tuple[str, ...]  # hex codes (rrggbb); empty when the palette file is missing
    canvas: tuple[int, int]
    preamble: str
    rules: tuple[str, ...]
    references: tuple[Path, ...]
    max_colors: int | None = None  # `colors = N` instead of a palette file

    def prompt(self, scale: int) -> str:
        """The kit as words, put before the request. It names the palette size, never its
        hex codes: image models read a list of codes as a mood, not a limit; a provider
        with palette input gets the palette itself, and the others a swatch reference."""
        w, h = self.canvas
        parts = [sentence(self.preamble)] if self.preamble else []
        parts.append(
            f"Pixel art, {w}x{h} pixels, each pixel drawn as a sharp {scale}x{scale} block; "
            "no anti-aliasing, no blur, no gradients between pixels."
        )
        if self.colors:
            parts.append(f"Keep to a limited palette of about {len(self.colors)} colours.")
        elif self.max_colors:
            parts.append(f"Use at most {self.max_colors} colours.")
        parts += [sentence(r) for r in self.rules]
        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "palette": self.palette,
            "colors": list(self.colors),
            "canvas": list(self.canvas),
            "preamble": self.preamble,
            "rules": list(self.rules),
            "references": [str(p) for p in self.references],
            "max_colors": self.max_colors,
        }


def sentence(text: str) -> str:
    """The text as a sentence: stripped, ending in . ! or ?"""
    text = text.strip()
    return text if not text or text[-1] in ".!?" else f"{text}."


def _table(raw: object, where: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ProjectError(f"pixelwright.toml: [{where}] must be a table")
    return raw


def _images(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)


def style_kit(target: Asset | tuple[Project, str]) -> StyleKit:
    """The kit for an asset, or for (project, "category[/sub]"): project `[style]`, then
    the category's."""
    project, rel = (target.project, target.rel) if isinstance(target, Asset) else target
    category = Path(rel).parts[0]
    style = _table(project.extra.get("style", {}), "style")
    raw = style.get(category)
    own: dict[str, Any] = raw if isinstance(raw, dict) else {}
    preamble = str(own.get("preamble", style.get("preamble", "")))
    rules = own.get("rules", style.get("rules", []))
    if not isinstance(rules, list) or not all(isinstance(r, str) for r in rules):
        raise ProjectError("pixelwright.toml: style rules must be a list of sentences")
    settings = project.settings_for(project.assets_dir / rel)
    file = project.palettes_dir / f"{settings.palette}.gpl"
    palette = read_palette(file) if file.is_file() and not settings.colors else None
    refs = _images(project.root / REFERENCES_DIR / category) + _images(
        project.root / REFERENCES_DIR
    )
    return StyleKit(
        category=category,
        palette=settings.palette,
        colors=tuple(c.hex for c in palette.colors) if palette else (),
        canvas=(settings.canvas["width"], settings.canvas["height"]),
        preamble=preamble,
        rules=tuple(rules),
        references=tuple(refs),
        max_colors=settings.colors,
    )
