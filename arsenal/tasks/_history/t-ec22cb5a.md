---
id: t-ec22cb5a
title: "T41: Guide"
label: "T41: Guide"
priority: 10
deps: [t-efb3204f]
tags: [m3]
status: merged
---

`docs/guide/how-it-works.md` (one drawspec diagram of the loop, glossary, "your first real asset"); README and `pw --help` link it; plugin skill `first-run`.

## Acceptance gate
Gate metric (from the plan): `make_check_exit_code == 0`. The tests below assert that threshold; the block fails if it does not hold.

```bash
make check
uv run pytest tests/plugin/test_skills.py -q
```

## Tests
`test_plugin_skills_reference_existing_commands` in `tests/plugin/test_skills.py` — `first-run` names only commands in the registry

## Location
docs, plugin
