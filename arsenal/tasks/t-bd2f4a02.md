---
id: t-bd2f4a02
title: "T46: Gemini"
label: "T46: Gemini"
priority: 5
deps: [t-fc975e68]
tags: [m3]
---

Gemini adapter. Built from the provider's current API docs at implementation time; capability flags, price per image, licence note, recorded responses with keys stripped. Real calls only in the owner's local session.

## Acceptance gate
Gate metric (from the plan): `make_check_exit_code == 0`. The tests below assert that threshold; the block fails if it does not hold.

```bash
make check
uv run pytest tests/core/test_gemini.py -q
```

## Tests
`test_gemini_img2img_sends_references_and_parses_image` in `tests/core/test_gemini.py` — request body matches the recorded shape; image decoded

## Location
core
