---
id: t-da19fb89
title: "T16: MCP server"
label: "T16: MCP server"
priority: 5
deps: [t-cabdce60]
tags: [m0-m1]
---

MCP server `pw mcp` from the same registry; image content for `render` capped at 1024 px.

## Acceptance gate
Gate metric (from the plan): `cli_mcp_parity_gaps == 0`. The test below asserts that threshold; the block fails if it does not hold.

```bash
make check
uv run pytest tests/mcp/test_parity.py -q
```

## Tests
`test_every_cli_command_has_matching_mcp_tool` in `tests/mcp/test_parity.py` — tool names and parameters equal the CLI registry

## Location
mcp
