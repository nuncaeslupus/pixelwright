---
id: t-a8d3eda5
title: "T53: Project model v2"
label: "T53: Project model v2"
priority: 5
tags: [m4]
status: merged
---

Project model v2: `pixelwright.toml` (palette library, export path, `keep_all_versions`, rules), `category.toml` (kind, palette, canvas, checks), nearest-folder resolution

## Acceptance gate
Gate metric (from the plan): `tests_failed == 0`. The block below checks what can be checked mechanically; the owner judges the rest.

```bash
make check
uv run pytest tests/test_project.py -q
```

## Tests
`test_settings_asset_in_category_uses_category_palette` in `tests/test_project.py` — an asset under a category with `palette = "night"` resolves to the night palette

## Location
core
