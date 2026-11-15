---
id: t-bec7d32c
title: "T2: OKLab"
label: "T2: OKLab"
priority: 10
deps: [t-2a519d6c]
tags: [m0-m1]
---

OKLab/OKLCH conversions and color distance.

## Acceptance gate
Gate metric (from the plan): `oklab_max_abs_error <= 0.001`. The test below asserts that threshold; the block fails if it does not hold.

```bash
make check
uv run pytest tests/core/test_color.py -q
```

## Tests
`test_oklab_reference_values_match_published` in `tests/core/test_color.py` — sRGB to OKLab matches Ottosson's published pairs within 1e-3

## Location
core.color
