---
id: t-31a81abf
title: "T64: Agent instructions"
label: "T64: Agent instructions"
priority: 5
deps: [t-a77f1792, t-12e402af]
tags: [m4]
status: merged
---

Agent instructions: rewrite Claude skills (style, critique-and-fix loop, listen with `pw wait`) and add `AGENTS.md`

## Acceptance gate
Gate metric (from the plan): `skills_invalid == 0`. The block below checks what can be checked mechanically; the owner judges the rest.

```bash
make check
uv run pytest tests/test_skills.py -q
```

## Tests
`test_skills_reference_existing_commands` in `tests/test_skills.py` — every `pw` command named in a skill exists

## Location
plugin
