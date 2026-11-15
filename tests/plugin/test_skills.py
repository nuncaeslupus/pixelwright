import re
from pathlib import Path

import pytest

from pixelwright.cli import REGISTRY

SKILLS = sorted((Path(__file__).parents[2] / "plugin" / "skills").glob("*/SKILL.md"))
PW_COMMAND = re.compile(r"\bpw ([a-z][a-z-]*)")


def test_the_plugin_ships_the_five_skills() -> None:
    names = {s.parent.name for s in SKILLS}
    assert names == {"review-loop", "critique", "zone-fix", "style-definition", "first-run"}


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_plugin_skills_reference_existing_commands(skill: Path) -> None:
    text = skill.read_text(encoding="utf-8")
    named = set(PW_COMMAND.findall(text))
    assert named, "a skill should drive pw"
    assert named - set(REGISTRY) - {"mcp"} == set()


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_skills_have_front_matter(skill: Path) -> None:
    head = skill.read_text(encoding="utf-8").split("---")[1]
    assert f"name: {skill.parent.name}\n" in head and "description: " in head
