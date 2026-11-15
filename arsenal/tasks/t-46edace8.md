---
id: t-46edace8
title: "T48: PixelLab"
label: "T48: PixelLab"
priority: 5
deps: [t-fc975e68]
tags: [m3]
---

PixelLab adapter. Built from the provider's current API docs at implementation time; capability flags, price per image, licence note, recorded responses with keys stripped. Real calls only in the owner's local session.

## Acceptance gate
Gate metric (from the plan): `make_check_exit_code == 0`. The tests below assert that threshold; the block fails if it does not hold.

```bash
make check
uv run pytest tests/core/test_pixellab.py -q
```

## Tests
`test_pixellab_inpaint_sends_mask` in `tests/core/test_pixellab.py` — mask in the body; image decoded

## Location
core
