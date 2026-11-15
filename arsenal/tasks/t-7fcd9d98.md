---
id: t-7fcd9d98
title: "T32: Viewer polish"
label: "T32: Viewer polish"
priority: 10
deps: [t-b32fd282, t-f66b337c, t-489a441e]
tags: [m2]
---

keyboard reachability, hover titles with shortcuts, both themes, a screenshot per screen for the record.

## Acceptance gate
Gate metric (from the plan): `e2e_failed == 0`. The tests below assert that threshold; the block fails if it does not hold.

```bash
make check
uv run pytest tests/viewer/e2e/test_a11y.py -q
```

## Tests
`test_every_control_has_a_title_and_shortcut` in `tests/viewer/e2e/test_a11y.py` — every button has a hover title; every mode reachable by keyboard; both themes render

## Location
viewer
