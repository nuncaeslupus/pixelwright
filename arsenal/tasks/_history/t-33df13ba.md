---
id: t-33df13ba
title: "T5: Workspace"
label: "T5: Workspace"
priority: 5
deps: [t-2a519d6c]
tags: [m0-m1]
status: merged
---

Workspace: `pixelwright.toml` roles/paths, stages, `.gitignore` writer, asset folder, versions, `meta.yaml`, `history.jsonl`, masks, schema versioning.

## Acceptance gate
Gate metric (from the plan): `schema_validation_failures == 0`. The test below asserts that threshold; the block fails if it does not hold.

```bash
make check
uv run pytest tests/workspace/test_versions.py -q
```

## Tests
`test_new_version_is_immutable_and_logged` in `tests/workspace/test_versions.py` — creating a version writes meta and one history line and never rewrites earlier versions

## Location
workspace
