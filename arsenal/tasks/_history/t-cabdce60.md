---
id: t-cabdce60
title: "T15: CLI pw"
label: "T15: CLI pw"
priority: 5
deps: [t-33df13ba, t-885ede2f, t-a644041a, t-4a9b180f, t-e3a4302c]
tags: [m0-m1]
status: merged
---

CLI `pw` with JSON envelope: init, new, attach, snap, quantize, clean, check, render, diff, mask, approve, reject, export, palette, style, prune.

## Acceptance gate
Gate metric (from the plan): `cli_contract_failures == 0`. The test below asserts that threshold; the block fails if it does not hold.

```bash
make check
uv run pytest tests/cli/test_envelope.py -q
```

## Tests
`test_cli_json_envelope_on_every_command` in `tests/cli/test_envelope.py` — each command's `--json` output validates against the envelope schema

## Location
cli
