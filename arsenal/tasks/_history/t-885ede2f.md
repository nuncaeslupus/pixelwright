---
id: t-885ede2f
title: "T6: Style"
label: "T6: Style"
priority: 10
deps: [t-9bdf9468, t-33df13ba]
tags: [m0-m1]
status: merged
---

Style guide format (`style.yaml` @1) and `style_version` on assets; bump and re-check listing.

## Acceptance gate
Gate metric (from the plan): `schema_validation_failures == 0`. The test below asserts that threshold; the block fails if it does not hold.

```bash
make check
uv run pytest tests/workspace/test_style.py -q
```

## Tests
`test_style_bump_records_version_on_new_assets` in `tests/workspace/test_style.py` — assets created after a bump carry the new style version

## Location
workspace.style
