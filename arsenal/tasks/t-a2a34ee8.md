---
id: t-a2a34ee8
title: "T8: Fixtures"
label: "T8: Fixtures"
priority: 5
deps: [t-2fe7505d]
tags: [m0-m1]
---

Synthetic fixtures: pseudo-pixel generator (upscale x2..x12, blur, sub-cell jitter, JPEG, noise) and detector case format.

## Acceptance gate
Gate metric (from the plan): `fixture_cases >= 200`. The test below asserts that threshold; the block fails if it does not hold.

```bash
make check
uv run pytest tests/fixtures/test_synth.py -q
```

## Tests
`test_fixture_generator_is_deterministic` in `tests/fixtures/test_synth.py` — same seed gives byte-identical cases

## Location
tests.fixtures
