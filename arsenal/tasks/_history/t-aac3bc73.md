---
id: t-aac3bc73
title: "T58: Version retention"
label: "T58: Version retention"
priority: 10
deps: [t-a77f1792]
tags: [m4]
status: merged
---

Retention: `keep_all_versions = false` prunes on finish, never input, v001, starred or final

## Acceptance gate
Gate metric (from the plan): `tests_failed == 0`. The block below checks what can be checked mechanically; the owner judges the rest.

```bash
make check
uv run pytest tests/test_retention.py -q
```

## Tests
`test_prune_setting_off_keeps_protected_versions` in `tests/test_retention.py` — after finish only protected versions remain; with the setting on, none are removed

## Location
core
