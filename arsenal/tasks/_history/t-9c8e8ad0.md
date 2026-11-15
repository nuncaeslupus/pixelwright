---
id: t-9c8e8ad0
title: "T51: Ranking"
label: "T51: Ranking"
priority: 1
deps: [t-dc179e50]
tags: [m3]
status: merged
---

Claude pairwise through MCP (`bench_pairs_next`, `bench_pair_record`), blind pairwise page in the viewer, Bradley-Terry, `report.html`, `pw bench apply` writes `[defaults]`.

## Acceptance gate
Gate metric (from the plan): `e2e_failed == 0`. The tests below assert that threshold; the block fails if it does not hold.

```bash
make check
uv run pytest tests/bench/test_rank.py -q
uv run pytest tests/viewer/e2e/test_blind.py -q
```

## Tests
`test_bradley_terry_recovers_known_order` in `tests/bench/test_rank.py` — synthetic pairs rank in the true order; `test_blind_page_hides_provider_names` in `tests/viewer/e2e/test_blind.py`

## Location
bench, viewer
