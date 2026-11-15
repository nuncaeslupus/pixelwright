---
id: t-efb3204f
title: "T40: tour"
label: "T40: tour"
priority: 5
deps: [t-37ccc6af]
tags: [m3]
---

steps with a "what happened / why / look at" block each; `--path` keeps the workspace; opens `pw view` at the end unless `--no-view`.

## Acceptance gate
Gate metric (from the plan): `tour_seconds <= 60`. The tests below assert that threshold; the block fails if it does not hold.

```bash
make check
uv run pytest tests/cli/test_tour.py -q
```

## Tests
`test_tour_runs_whole_loop_offline` in `tests/cli/test_tour.py` — exits 0 with network blocked, ends with an exported asset and one approved version

## Location
cli
