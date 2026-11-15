---
id: t-24bf4f4e
title: "T20: Issue and inbox commands"
label: "T20: Issue and inbox commands"
priority: 5
deps: [t-c347f49a]
tags: [m2]
---

`pw issue add|list|resolve`, `pw history`, `pw status <id>`, `pw inbox [--since]`; MCP mirrors from the registry.

## Acceptance gate
Gate metric (from the plan): `make_check_exit_code == 0`. The tests below assert that threshold; the block fails if it does not hold.

```bash
make check
uv run pytest tests/cli/test_inbox.py -q
```

## Tests
`test_inbox_since_lists_new_versions_and_decisions` in `tests/cli/test_inbox.py` — only events after `--since` are returned

## Location
cli, mcp
