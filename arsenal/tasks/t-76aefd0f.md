---
id: t-76aefd0f
title: "T73: Game style kit"
label: "T73: Game style kit"
priority: 1
deps: [t-76a6c43f]
tags: [m6]
---

One style kit per project (and per category): palette, native size, pixel rules, reference images in `style/references/` and a prompt preamble. `pw generate` always sends it (palette as hex codes or provider palette input, references as image inputs where supported), and normalise uses the same palette and canvas, so 'for my game, an empty old bar with a stage and a piano under spotlights' comes back in the game's style. `pw style show` prints the kit.

## Acceptance gate
Gate metric (from the plan): `tests_failed == 0`.

```bash
make check
uv run pytest tests/test_style_kit.py -q
```

## Tests
`test_generate_sends_style_kit` in `tests/test_style_kit.py`: with a kit set, the replay provider receives the palette codes, preamble and references

## Location
core
