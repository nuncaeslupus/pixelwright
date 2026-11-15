---
id: t-ecfdc5ce
title: "T44: Candidates"
label: "T44: Candidates"
priority: 5
deps: [t-e0b2016c]
tags: [m3]
---

Compare offers siblings sharing a request hash; pick one, reject the rest.

## Acceptance gate
Gate metric (from the plan): `e2e_failed == 0`. The tests below assert that threshold; the block fails if it does not hold.

```bash
make check
uv run pytest tests/viewer/e2e/test_candidates.py -q
```

## Tests
`test_compare_shows_candidates_of_one_generate` in `tests/viewer/e2e/test_candidates.py` — siblings with the same request_hash appear side by side

## Location
viewer
