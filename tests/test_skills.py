from __future__ import annotations

import re
from pathlib import Path

import pytest

from pixelwright.cli.registry import REGISTRY
from pixelwright.project import AGENTS_TEMPLATE, init_project

ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted((ROOT / "plugin" / "skills").glob("*/SKILL.md"))
DOCS = [*SKILLS, AGENTS_TEMPLATE]
PW = re.compile(r"`pw ([a-z][a-z-]*)")


def test_skills_exist() -> None:
    assert {p.parent.name for p in SKILLS} == {"pixelwright", "listen", "style"}


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.parent.name + "/" + p.name)
def test_skills_reference_existing_commands(doc: Path) -> None:
    named = set(PW.findall(doc.read_text(encoding="utf-8")))
    assert named, f"{doc} names no pw command"
    assert named <= set(REGISTRY), sorted(named - set(REGISTRY))


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_skill_frontmatter(skill: Path) -> None:
    text = skill.read_text(encoding="utf-8")
    head = text.split("---")[1]
    assert f"name: {skill.parent.name}" in head
    desc = next(line for line in head.splitlines() if line.startswith("description: "))
    assert 40 < len(desc) < 1024


def test_init_writes_agents_md(tmp_path: Path) -> None:
    project = init_project(tmp_path / "art")
    assert (project.root / "AGENTS.md").read_text() == AGENTS_TEMPLATE.read_text()
