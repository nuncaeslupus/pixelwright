---
id: t-823adbf8
title: "T23: Diff deltas"
label: "T23: Diff deltas"
priority: 10
tags: [m2]
status: merged
---

`pw diff` adds per-check deltas, changed pixel count and share, colors used, bounding box.

## Acceptance gate
Gate metric (from the plan): `make_check_exit_code == 0`. The tests below assert that threshold; the block fails if it does not hold.

```bash
make check
uv run pytest tests/cli/test_diff.py -q
```

## Tests
`test_diff_reports_check_deltas_and_changed_area` in `tests/cli/test_diff.py` — deltas per check, changed count and bounding box

## Location
cli
