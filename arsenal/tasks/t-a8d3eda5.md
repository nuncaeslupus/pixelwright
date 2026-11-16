---
id: t-a8d3eda5
title: "T53: Project model v2"
label: "T53: Project model v2"
priority: 5
tags: [m4]
---

Project model v2: `pixelwright.toml` (palette library, export path, `keep_all_versions`, rules), `group.toml`, nearest-folder resolution

## Acceptance gate
Gate metric (from the plan): `tests_failed == 0`. The block below checks what can be checked mechanically; the owner judges the rest.

```bash
make check
uv run pytest tests/test_project.py -q
```

## Tests
`test_settings_asset_in_group_uses_group_palette` in `tests/test_project.py` — an asset under a group with `palette = "night"` resolves to the night palette

## Location
core
