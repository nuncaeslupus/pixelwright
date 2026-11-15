"""Writes the pixelwright-managed block of the workspace `.gitignore` from the commit stages."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from pixelwright.workspace.config import WorkspaceConfig
from pixelwright.workspace.files import write_bytes_atomic

BEGIN = "# >>> pixelwright (managed; edit `commit` in pixelwright.toml) >>>"
END = "# <<< pixelwright <<<"


def managed_lines(config: WorkspaceConfig, approved: Iterable[str] = ()) -> list[str]:
    """Ignore patterns for the stages not committed.

    `approved` lists version folders (relative to the workspace root) whose stage is
    `approved`; they are re-included when drafts are ignored but approvals are kept.
    """
    assets = config.roles["assets"].rstrip("/")
    lines = [f"/{config.roles['cache'].rstrip('/')}/"]
    if "experiment" not in config.commit:
        lines += [f"/{config.roles['experiments'].rstrip('/')}/", f"/{assets}/*/drafts/"]
    if "draft" not in config.commit:
        lines.append(f"/{assets}/*/versions/*/")
        if "approved" in config.commit:
            lines += [f"!/{p.strip('/')}/" for p in sorted(approved)]
    elif "approved" not in config.commit:
        lines += [f"/{p.strip('/')}/" for p in sorted(approved)]
    if "final" not in config.commit:
        lines.append(f"/{assets}/*/export/")
        lines += [f"/{p.rstrip('/')}/" for p in sorted(set(config.exports.values()))]
    return lines


def write_gitignore(root: Path, config: WorkspaceConfig, approved: Iterable[str] = ()) -> None:
    """Replace the managed block, keeping every line outside it."""
    path = root / ".gitignore"
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    kept: list[str] = []
    inside = False
    for line in existing:
        if line == BEGIN:
            inside = True
        elif line == END:
            inside = False
        elif not inside:
            kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()
    block = [BEGIN, *managed_lines(config, approved), END]
    text = "\n".join([*kept, "", *block] if kept else block) + "\n"
    write_bytes_atomic(path, text.encode("utf-8"))
