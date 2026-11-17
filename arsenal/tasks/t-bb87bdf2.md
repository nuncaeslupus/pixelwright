---
id: t-bb87bdf2
title: "T61: Project screen"
label: "T61: Project screen"
priority: 5
deps: [t-4e92063d, t-a77f1792]
tags: [m4]
---

Project screen: assets by category with filters (waiting on, state), state, next step and actor; add dialog with category; folder watching

## Acceptance gate
Gate metric (from the plan): `e2e_failed == 0`. The block below checks what can be checked mechanically; the owner judges the rest.

```bash
make check
uv run pytest tests/e2e/test_project_screen.py -q
```

## Tests
`test_project_screen_shows_next_step` in `tests/e2e/test_project_screen.py` — each asset card shows one next step

## Location
app
