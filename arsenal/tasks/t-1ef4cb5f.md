---
id: t-1ef4cb5f
title: "T26: Style and palette edit"
label: "T26: Style and palette edit"
priority: 5
tags: [m2]
---

`style propose` (palette families and ramps from references), `style test` (checks on the style's test assets), `palette edit` (set, add, remove, reorder colors; ramps re-checked).

## Acceptance gate
Gate metric (from the plan): `make_check_exit_code == 0`. The tests below assert that threshold; the block fails if it does not hold.

```bash
make check
uv run pytest tests/cli/test_style.py -q
```

## Tests
`test_style_test_reports_per_asset_results` in `tests/cli/test_style.py` — `style test` runs checks on the style's test assets

## Location
workspace, cli
