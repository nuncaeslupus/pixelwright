from pathlib import Path

import pytest

from pixelwright.core.palette import Color, Palette, Ramp, Ramps
from pixelwright.io import palette_io

PALETTE = Palette(
    [
        Color(20, 12, 28, "Night Ink"),
        Color(68, 36, 52, "plum"),
        Color(255, 255, 255),
        Color(48, 52, 109, "deep blue sea"),
        Color(0, 0, 0, "black"),
    ],
    name="harbour night",
    columns=4,
)


def test_gpl_roundtrip_preserves_order_and_names(tmp_path: Path) -> None:
    path = tmp_path / "harbour.gpl"
    palette_io.write_palette(path, PALETTE)
    back = palette_io.read_palette(path)
    assert back == PALETTE  # order, names, palette name and columns


def test_hex_roundtrip_keeps_order(tmp_path: Path) -> None:
    path = tmp_path / "harbour.hex"
    palette_io.write_palette(path, PALETTE)
    back = palette_io.read_palette(path)
    assert [c.rgb for c in back] == [c.rgb for c in PALETTE]
    assert back.name == "harbour"


def test_reads_real_world_gpl_variants() -> None:
    text = "GIMP Palette\nName: x\n# comment\n\n  0   0   0\tBlack\n255 128 0 Bright orange\n"
    palette = palette_io.parse_gpl(text)
    assert [(c.rgb, c.name) for c in palette] == [
        ((0, 0, 0), "Black"),
        ((255, 128, 0), "Bright orange"),
    ]


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("JASC-PAL\n", "header"),
        ("GIMP Palette\n1 2\n", "line 2"),
        ("GIMP Palette\n1 2 300\n", "range"),
    ],
)
def test_gpl_errors(text: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        palette_io.parse_gpl(text)


def test_hex_accepts_hash_and_comments() -> None:
    palette = palette_io.parse_hex("#ff0000\n00ff00 ; green\n\n")
    assert [c.hex for c in palette] == ["ff0000", "00ff00"]
    with pytest.raises(ValueError, match="RRGGBB"):
        palette_io.parse_hex("12345\n")


def test_ramps_roundtrip_and_range_check(tmp_path: Path) -> None:
    ramps = Ramps(
        {"wood": Ramp((0, 1, 3)), "water": Ramp((3, 2), cycle=True, note="loop")},
        palette="harbour.gpl",
    )
    path = tmp_path / "ramps.yaml"
    palette_io.write_ramps(path, ramps)
    assert palette_io.read_ramps(path) == ramps
    ramps.check_against(PALETTE)
    with pytest.raises(ValueError, match="out of palette range"):
        Ramps({"bad": Ramp((0, 9))}).check_against(PALETTE)


def test_unknown_extension_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported"):
        palette_io.write_palette(tmp_path / "x.act", PALETTE)
