"""Palette files: GIMP `.gpl`, plain `.hex` (one RRGGBB per line) and `ramps.yaml`."""

from __future__ import annotations

from pathlib import Path

from pixelwright.core.palette import Color, Palette, Ramp, Ramps
from pixelwright.workspace import schema
from pixelwright.workspace.files import read_yaml, write_bytes_atomic, write_yaml

GPL_HEADER = "GIMP Palette"


def parse_gpl(text: str) -> Palette:
    lines = text.splitlines()
    if not lines or lines[0].strip() != GPL_HEADER:
        raise ValueError("not a GIMP palette: missing 'GIMP Palette' header")
    name, columns, colors = "", 0, []
    for lineno, raw in enumerate(lines[1:], start=2):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("Name:"):
            name = line[5:].strip()
            continue
        if line.startswith("Columns:"):
            columns = int(line[8:].strip() or 0)
            continue
        parts = line.split(None, 3)
        try:
            r, g, b = (int(p) for p in parts[:3])
        except ValueError as exc:
            raise ValueError(f"line {lineno}: expected 'R G B [name]': {raw!r}") from exc
        colors.append(Color(r, g, b, parts[3].strip() if len(parts) > 3 else ""))
    return Palette(colors, name=name, columns=columns)


def format_gpl(palette: Palette) -> str:
    out = [GPL_HEADER, f"Name: {palette.name}"]
    if palette.columns:
        out.append(f"Columns: {palette.columns}")
    out.append("#")
    for c in palette:
        row = f"{c.r:3d} {c.g:3d} {c.b:3d}"
        out.append(f"{row}\t{c.name}" if c.name else row)
    return "\n".join(out) + "\n"


def parse_hex(text: str, name: str = "") -> Palette:
    colors = []
    for raw in text.splitlines():
        line = raw.split(";")[0].strip()
        if line:
            colors.append(Color.from_hex(line))
    return Palette(colors, name=name)


def format_hex(palette: Palette) -> str:
    return "".join(f"{c.hex}\n" for c in palette)


def read_palette(path: Path) -> Palette:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".gpl":
        return parse_gpl(text)
    if suffix == ".hex":
        return parse_hex(text, name=path.stem)
    raise ValueError(f"unsupported palette format: {path.suffix} (use .gpl or .hex)")


def write_palette(path: Path, palette: Palette) -> None:
    suffix = path.suffix.lower()
    if suffix == ".gpl":
        text = format_gpl(palette)
    elif suffix == ".hex":
        text = format_hex(palette)
    else:
        raise ValueError(f"unsupported palette format: {path.suffix} (use .gpl or .hex)")
    write_bytes_atomic(path, text.encode("utf-8"))


def read_ramps(path: Path) -> Ramps:
    data = schema.validate("ramps", read_yaml(path))
    ramps = {}
    for name, entry in data["ramps"].items():
        if not isinstance(entry, dict) or not isinstance(entry.get("ramp"), list):
            raise schema.SchemaError(f"ramps: {name!r} needs a 'ramp' list of indices")
        ramps[str(name)] = Ramp(
            tuple(int(i) for i in entry["ramp"]),
            cycle=bool(entry.get("cycle", False)),
            note=str(entry.get("note", "")),
        )
    return Ramps(ramps, palette=str(data.get("palette", "")))


def write_ramps(path: Path, ramps: Ramps) -> None:
    entries: dict[str, dict[str, object]] = {}
    for name, ramp in ramps.ramps.items():
        entry: dict[str, object] = {"ramp": list(ramp.indices)}
        if ramp.cycle:
            entry["cycle"] = True
        if ramp.note:
            entry["note"] = ramp.note
        entries[name] = entry
    data: dict[str, object] = {"ramps": entries}
    if ramps.palette:
        data = {"palette": ramps.palette, **data}
    write_yaml(path, schema.stamp("ramps", data))
