"""`critique.md`: Claude's pairwise critique of a version, complaints linked to issues.

Format: YAML front matter (`schema`, `version`, `compared_to`, `verdict`), then one
`## <title>` section per complaint whose first lines are `issue: <id>` and `rule: <id>`,
then free Markdown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from pixelwright.workspace import schema

_HEAD = re.compile(r"^(issue|rule):\s*(.*)$")


@dataclass
class Complaint:
    title: str
    issue: str = ""
    rule: str = ""
    body: str = ""


@dataclass
class Critique:
    version: str
    verdict: str
    compared_to: str | None = None
    complaints: list[Complaint] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "compared_to": self.compared_to,
            "verdict": self.verdict,
            "complaints": [vars(c) for c in self.complaints],
        }


def render(c: Critique) -> str:
    head = {"version": c.version, "compared_to": c.compared_to, "verdict": c.verdict}
    front = yaml.safe_dump(schema.stamp("critique", head), sort_keys=False, allow_unicode=True)
    parts = [f"---\n{front}---\n"]
    for k in c.complaints:
        lines = [f"## {k.title}"]
        lines += [f"issue: {k.issue}"] if k.issue else []
        lines += [f"rule: {k.rule}"] if k.rule else []
        parts.append("\n".join(lines) + ("\n\n" + k.body.strip() if k.body.strip() else "") + "\n")
    return "\n".join(parts)


def parse(text: str) -> Critique:
    if not text.startswith("---\n"):
        raise schema.SchemaError("critique.md must start with YAML front matter")
    front, sep, rest = text[4:].partition("\n---\n")
    if not sep:
        raise schema.SchemaError("critique.md front matter is not closed")
    head = schema.validate("critique", yaml.safe_load(front))
    complaints = []
    for block in re.split(r"(?m)^## ", rest)[1:]:
        title, _, body = block.partition("\n")
        k = Complaint(title.strip())
        lines = body.strip("\n").splitlines()
        while lines and (m := _HEAD.match(lines[0].strip())):
            setattr(k, m.group(1), m.group(2).strip())
            lines.pop(0)
        k.body = "\n".join(lines).strip()
        complaints.append(k)
    compared = head.get("compared_to")
    return Critique(head["version"], head["verdict"], compared, complaints)
