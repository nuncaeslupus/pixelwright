---
id: t-37ccc6af
title: "T38: Next step"
label: "T38: Next step"
priority: 5
deps: [t-e0b2016c]
tags: [m3]
status: merged
---

states (no source, sketch only, raw generated, snapped, quantized, cleaned, checks failing, open issues, ready to approve, approved, exported) → command and one-line why; `pw next`; the viewer shows it in the empty side panel and status bar.

## Acceptance gate
Gate metric (from the plan): `e2e_failed == 0`. The tests below assert that threshold; the block fails if it does not hold.

```bash
make check
uv run pytest tests/workspace/test_next_step.py -q
```

## Tests
`test_next_step_covers_every_asset_state` in `tests/workspace/test_next_step.py` — every state maps to a command that exists in the registry

## Location
workspace, viewer
