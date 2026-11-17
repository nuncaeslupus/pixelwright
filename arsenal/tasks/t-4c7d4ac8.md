---
id: t-4c7d4ac8
title: "T55: Issues and fixes log"
label: "T55: Issues and fixes log"
priority: 5
deps: [t-b2c24f25]
tags: [m4]
---

Issues and fixes log (`issues.jsonl`): schema, append, events; fix candidates as images; accepting one or several fixes writes one new version; reject with reason; reply; mark fixed; undo/redo

## Acceptance gate
Gate metric (from the plan): `tests_failed == 0`. The block below checks what can be checked mechanically; the owner judges the rest.

```bash
make check
uv run pytest tests/test_issues.py -q
```

## Tests
`test_fix_accept_writes_new_version` in `tests/test_issues.py` — accepting a fix adds exactly one version and links it

## Location
core
