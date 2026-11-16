---
id: t-4c7d4ac8
title: "T55: Advice log"
label: "T55: Advice log"
priority: 5
deps: [t-b2c24f25]
tags: [m4]
---

Advice log: schema, append, state events, accept runs fix into a new version, reject with reason

## Acceptance gate
Gate metric (from the plan): `tests_failed == 0`. The block below checks what can be checked mechanically; the owner judges the rest.

```bash
make check
uv run pytest tests/test_advice.py -q
```

## Tests
`test_advice_accept_with_fix_writes_new_version` in `tests/test_advice.py` — accepting advice with a fix adds exactly one version and links it

## Location
core
